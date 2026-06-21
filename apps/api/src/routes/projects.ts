// Copyright (c) 2025 Devayan Dewri. All rights reserved.
import type { ApiErrorCode, CutList, EditMode, StyleTier } from "@ai-video-editor/shared-types";
import { isApiErrorCode } from "@ai-video-editor/shared-types";
import { and, desc, eq, inArray } from "drizzle-orm";
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { FastifyInstance } from "fastify";
import fs from "fs";
import os from "os";
import path from "path";
import { db } from "../db";
import { assets, generationJobs, projects, renders } from "../db/schema";
import { cacheDel, cacheGet, cacheSet } from "../lib/cache";
import { createCompletionToken } from "../lib/crypto";
import { buildInitialCutList } from "../lib/cutlist";
import { sendError } from "../lib/errors";
import { slidingWindowCheck } from "../lib/rateLimit";
import { validatePromptGuardrails } from "../middleware/guardrails";
import { enforceTokenBudget, incrementTokenUsage } from "../middleware/tokenBudget";
import {
  createProjectSchema,
  generateFromReferenceSchema,
  patchProjectSchema,
  promptEditSchema,
  updateCutlistSchema,
  validateBody,
} from "../middleware/validate";
import { applyPromptEdit, transcribeAudio } from "../services/ai";
import { enqueueJob, publishProgress } from "../services/queue";
import { deleteProjectAssets, downloadAsset } from "../services/storage";
import {
  getStyleAnalysisFromWorkflow,
  sendCutlistApprovedSignal,
  startGenerateCutlistWorkflow,
} from "../services/temporal";

export async function projectRoutes(app: FastifyInstance) {
  // List projects for user
  app.get("/", async (request, reply) => {
    const userId = request.userId;
    if (!userId) {
      return sendError(reply, 401, "Unauthorized", "UNAUTHORIZED");
    }
    const cacheKey = `projects:list:${userId}`;
    const cached = await cacheGet<typeof userProjects>(cacheKey);
    if (cached) {
      return { projects: cached };
    }
    const userProjects = await db.query.projects.findMany({
      where: eq(projects.userId, userId),
      orderBy: [desc(projects.updatedAt)],
      with: {
        assets: true,
      },
    });
    await cacheSet(cacheKey, userProjects);
    return { projects: userProjects };
  });

  // Create project
  app.post("/", { preHandler: validateBody(createProjectSchema) }, async (request, reply) => {
    const body = request.validatedBody as { name: string; styleTier?: StyleTier; mode?: EditMode };
    const userId = request.userId;
    if (!userId) {
      return sendError(reply, 401, "Unauthorized", "UNAUTHORIZED");
    }

    const [project] = await db
      .insert(projects)
      .values({
        name: body.name || "Untitled Project",
        status: "uploading",
        userId,
        styleTier: body.styleTier || "with_effects",
        mode: body.mode || "auto",
        clipAssetIds: [],
      })
      .returning();

    await cacheDel(`projects:list:${userId}`);
    return { project };
  });

  // Get project
  app.get("/:id", async (request, reply) => {
    const { id } = request.params as { id: string };
    const userId = request.userId;
    const project = await db.query.projects.findFirst({
      where: eq(projects.id, id),
      with: { assets: true },
    });
    if (!project) {
      return sendError(reply, 404, "Not found", "NOT_FOUND");
    }
    if (project.userId !== userId) {
      return sendError(reply, 403, "Forbidden", "FORBIDDEN");
    }
    return { project };
  });

  // Get cached or live style analysis for the project's reference video
  app.get("/:id/style", async (request, reply) => {
    const { id } = request.params as { id: string };
    const userId = request.userId;
    const project = await db.query.projects.findFirst({
      where: eq(projects.id, id),
    });
    if (!project) {
      return sendError(reply, 404, "Not found", "NOT_FOUND");
    }
    if (project.userId !== userId) {
      return sendError(reply, 403, "Forbidden", "FORBIDDEN");
    }

    // Return cached analysis if already stored.
    if (project.styleAnalysis) {
      return { styleAnalysis: project.styleAnalysis };
    }

    // Otherwise try to fetch from the running/completed style workflow.
    if (!project.referenceAssetId) {
      return sendError(reply, 422, "Project has no reference video", "MISSING_ASSETS");
    }

    const analysis = await getStyleAnalysisFromWorkflow(project.referenceAssetId);
    if (!analysis) {
      return sendError(reply, 202, "Style analysis not yet available", "PENDING");
    }

    // Cache result for future requests.
    await db
      .update(projects)
      .set({ styleAnalysis: analysis, updatedAt: new Date() })
      .where(eq(projects.id, id));

    return { styleAnalysis: analysis };
  });

  // Update project
  app.patch("/:id", { preHandler: validateBody(patchProjectSchema) }, async (request, reply) => {
    const { id } = request.params as { id: string };
    const userId = request.userId;
    const project = await db.query.projects.findFirst({
      where: eq(projects.id, id),
    });
    if (!project) {
      return sendError(reply, 404, "Not found", "NOT_FOUND");
    }
    if (project.userId !== userId) {
      return sendError(reply, 403, "Forbidden", "FORBIDDEN");
    }

    const body = request.validatedBody as Partial<typeof projects.$inferInsert>;
    const [updated] = await db
      .update(projects)
      .set({ ...body, updatedAt: new Date() })
      .where(eq(projects.id, id))
      .returning();

    await cacheDel(`projects:list:${userId}`);
    return { project: updated };
  });

  // Update cut-list (assisted mode)
  app.patch("/:id/cutlist", { preHandler: validateBody(updateCutlistSchema) }, async (request, reply) => {
    const { id } = request.params as { id: string };
    const userId = request.userId;
    if (!userId) {
      return sendError(reply, 401, "Unauthorized", "UNAUTHORIZED");
    }
    const project = await db.query.projects.findFirst({
      where: eq(projects.id, id),
    });
    if (!project) {
      return sendError(reply, 404, "Not found", "NOT_FOUND");
    }
    if (project.userId !== userId) {
      return sendError(reply, 403, "Forbidden", "FORBIDDEN");
    }

    const body = request.validatedBody as { cutList: CutList };
    const [updated] = await db
      .update(projects)
      .set({
        cutList: body.cutList,
        status: "rendering",
        updatedAt: new Date(),
      })
      .where(eq(projects.id, id))
      .returning();

    const activeRender = await db.query.renders.findFirst({
      where: and(eq(renders.projectId, id), inArray(renders.status, ["queued", "running"])),
    });
    if (activeRender?.workflowId) {
      await sendCutlistApprovedSignal(activeRender.workflowId, body.cutList);
    }

    await cacheDel(`projects:list:${userId}`);
    return { project: updated };
  });

  type StartGenerationResult =
    | { ok: true; job: typeof generationJobs.$inferSelect; project: typeof projects.$inferSelect }
    | { ok: false; status: number; message: string; code: ApiErrorCode; extra?: Record<string, unknown> };

  async function startGenerationAtomic(
    projectId: string,
    userId: string,
    options?: Record<string, unknown>,
  ): Promise<StartGenerationResult> {
    const values = {
      projectId,
      status: "queued" as const,
      stage: "queued" as const,
      progress: 0,
      options: options || null,
      startedAt: new Date(),
    };

    if (typeof db.transaction === "function") {
      return db.transaction(async (tx): Promise<StartGenerationResult> => {
        const [project] = await tx.select().from(projects).where(eq(projects.id, projectId)).for("update");
        if (!project) {
          return { ok: false, status: 404, message: "Project not found", code: "NOT_FOUND" };
        }
        if (project.userId !== userId) {
          return { ok: false, status: 403, message: "Forbidden", code: "FORBIDDEN" };
        }
        if (!project.referenceAssetId) {
          return {
            ok: false,
            status: 422,
            message: "Project missing reference video",
            code: "MISSING_ASSETS",
          };
        }
        if (!project.songAssetId) {
          return { ok: false, status: 422, message: "Project missing song asset", code: "MISSING_ASSETS" };
        }

        const existing = await tx.query.generationJobs.findFirst({
          where: and(
            eq(generationJobs.projectId, projectId),
            inArray(generationJobs.status, ["queued", "running"]),
          ),
        });
        if (existing) {
          return {
            ok: false,
            status: 409,
            message: "Generation already in progress",
            code: "GENERATION_ALREADY_RUNNING",
            extra: { jobId: existing.id },
          };
        }

        const [job] = await tx.insert(generationJobs).values(values).returning();
        return { ok: true, job, project };
      });
    }

    const project = await db.query.projects.findFirst({ where: eq(projects.id, projectId) });
    if (!project) {
      return { ok: false, status: 404, message: "Project not found", code: "NOT_FOUND" };
    }
    if (project.userId !== userId) {
      return { ok: false, status: 403, message: "Forbidden", code: "FORBIDDEN" };
    }
    if (!project.referenceAssetId) {
      return { ok: false, status: 422, message: "Project missing reference video", code: "MISSING_ASSETS" };
    }
    if (!project.songAssetId) {
      return { ok: false, status: 422, message: "Project missing song asset", code: "MISSING_ASSETS" };
    }

    const existing = await db.query.generationJobs.findFirst({
      where: and(
        eq(generationJobs.projectId, projectId),
        inArray(generationJobs.status, ["queued", "running"]),
      ),
    });
    if (existing) {
      return {
        ok: false,
        status: 409,
        message: "Generation already in progress",
        code: "GENERATION_ALREADY_RUNNING",
        extra: { jobId: existing.id },
      };
    }

    const [job] = await db.insert(generationJobs).values(values).returning();
    return { ok: true, job, project };
  }

  // Generate a cutlist from the reference video and song
  app.post(
    "/:id/generate",
    { preHandler: validateBody(generateFromReferenceSchema) },
    async (request, reply) => {
      const { id } = request.params as { id: string };
      const userId = request.userId;
      const body = request.validatedBody as { prompt?: string; options?: Record<string, unknown> };

      const options = (body.options || undefined) as Record<string, unknown> | undefined;
      const startResult = await startGenerationAtomic(id, userId, options);
      if (!startResult.ok) {
        return sendError(reply, startResult.status, startResult.message, startResult.code, startResult.extra);
      }

      const { job, project } = startResult;
      const completionToken = createCompletionToken(job.id, project.id);

      // Resolve style analysis if it is not already cached.
      let styleAnalysis = (project.styleAnalysis as Record<string, unknown> | null) ?? undefined;
      if (!styleAnalysis && project.referenceAssetId) {
        styleAnalysis = (await getStyleAnalysisFromWorkflow(project.referenceAssetId)) ?? undefined;
        if (styleAnalysis) {
          await db.update(projects).set({ styleAnalysis, updatedAt: new Date() }).where(eq(projects.id, id));
        }
      }
      if (!styleAnalysis) {
        await db.delete(generationJobs).where(eq(generationJobs.id, job.id));
        return sendError(reply, 202, "Style analysis not yet available", "PENDING");
      }

      const assetIds = [
        project.referenceAssetId,
        project.songAssetId,
        ...((project.clipAssetIds as string[]) || []),
      ].filter((id): id is string => Boolean(id));

      const assetRows =
        (assetIds.length
          ? await db.query.assets.findMany({
              where: (table, { inArray }) => inArray(table.id, assetIds),
              columns: { id: true, storageKey: true },
            })
          : []) ?? [];

      const assetKeyMap: Record<string, string> = {};
      for (const row of assetRows) {
        if (row?.id && row?.storageKey) {
          assetKeyMap[row.id] = row.storageKey;
        }
      }

      let workflowId: string;
      try {
        workflowId = await startGenerateCutlistWorkflow({
          projectId: project.id,
          generationJobId: job.id,
          userId,
          referenceAssetId: project.referenceAssetId,
          songAssetId: project.songAssetId!,
          clipAssetIds: (project.clipAssetIds as string[]) || [],
          styleAnalysis,
          assetKeyMap,
          completionToken,
          options,
        });
      } catch (e) {
        const errorMessage = e instanceof Error ? e.message : String(e);
        await db
          .update(generationJobs)
          .set({ status: "failed", errorMessage })
          .where(eq(generationJobs.id, job.id));
        return sendError(reply, 500, "Generation engine unavailable", "TEMPORAL_ERROR");
      }

      await db.update(generationJobs).set({ workflowId }).where(eq(generationJobs.id, job.id));

      await enqueueJob({
        jobId: job.id,
        projectId: id,
        type: "cutlist_generation",
        payload: options || {},
        priority: 1,
        createdAt: new Date().toISOString(),
      });

      await publishProgress(job.id, "queued", 0, "Generation queued");

      return { job: { ...job, workflowId } };
    },
  );

  // Get latest generation job for a project
  app.get("/:id/generation", async (request, reply) => {
    const { id } = request.params as { id: string };
    const userId = request.userId;

    const project = await db.query.projects.findFirst({ where: eq(projects.id, id) });
    if (!project) {
      return sendError(reply, 404, "Project not found", "NOT_FOUND");
    }
    if (project.userId !== userId) {
      return sendError(reply, 403, "Forbidden", "FORBIDDEN");
    }

    const job = await db.query.generationJobs.findFirst({
      where: eq(generationJobs.projectId, id),
      orderBy: [desc(generationJobs.createdAt)],
    });

    if (!job) {
      return sendError(reply, 404, "No generation job found", "NOT_FOUND");
    }

    return { job };
  });

  // Transcribe audio asset to subtitles
  app.post(
    "/:id/transcribe",
    {
      preHandler: validatePromptGuardrails,
      config: {
        rateLimit: {
          max: 5,
          timeWindow: "1 minute",
        },
      },
    },
    async (request, reply) => {
      const { id } = request.params as { id: string };
      const userId = request.userId;
      const project = await db.query.projects.findFirst({
        where: eq(projects.id, id),
      });
      if (!project) {
        return sendError(reply, 404, "Not found", "NOT_FOUND");
      }
      if (project.userId !== userId) {
        return sendError(reply, 403, "Forbidden", "FORBIDDEN");
      }

      const body = request.body as { assetId?: string };
      if (!body?.assetId) {
        return sendError(reply, 400, "assetId required", "VALIDATION_ERROR");
      }

      const asset = await db.query.assets.findFirst({
        where: eq(assets.id, body.assetId),
      });
      if (!asset || asset.projectId !== id) {
        return sendError(reply, 404, "Asset not found", "NOT_FOUND");
      }

      const tmpDir = os.tmpdir();
      const tmpFile = path.join(tmpDir, `transcribe-${asset.id}-${Date.now()}.mp3`);

      try {
        await downloadAsset(asset.storageKey, tmpFile);
        const audioBuffer = fs.readFileSync(tmpFile);
        const segments = await transcribeAudio(userId, audioBuffer, asset.filename);

        const subtitles = segments.map((s, i) => ({
          id: `sub-${i}`,
          text: s.text,
          startS: s.start,
          endS: s.end,
        }));

        return { subtitles };
      } catch (err) {
        request.log.error({ err }, "Transcription failed");
        const rawCode =
          err && typeof err === "object" && "code" in err ? (err as { code?: string }).code : undefined;
        const code: ApiErrorCode = isApiErrorCode(rawCode) ? rawCode : "INTERNAL_ERROR";
        const status =
          code === "PROVIDER_KEY_MISSING" || code === "AI_REFUSED"
            ? 400
            : code === "CUTLIST_SCHEMA_DRIFT" || code === "AI_INVALID_JSON"
              ? 422
              : 500;
        if (err instanceof Error) {
          const message = err.message || "Transcription failed";
          return sendError(reply, status, message, code);
        }
        return sendError(reply, status, "Transcription failed", code);
      } finally {
        try {
          fs.unlinkSync(tmpFile);
        } catch {
          // ignore cleanup errors
        }
      }
    },
  );

  // Prompt-to-edit (AI powered)
  app.post(
    "/:id/prompt",
    {
      preHandler: [
        validateBody(promptEditSchema),
        validatePromptGuardrails,
        enforceTokenBudget,
        async (request, reply) => {
          if (process.env.E2E === "1") return;
          const userId = request.userId;
          if (!userId) {
            return sendError(reply, 401, "Unauthorized", "UNAUTHORIZED");
          }
          const rl = await slidingWindowCheck({
            key: `rl:prompt:${userId}`,
            limit: 10,
            windowMs: 60_000,
            failClosed: true,
          });
          if (!rl.allowed) {
            return sendError(
              reply,
              429,
              `Rate limit exceeded. Try again in ${Math.ceil((rl.resetMs - Date.now()) / 1000)}s.`,
              "RATE_LIMITED",
              { resetMs: rl.resetMs, limit: rl.limit },
            );
          }
        },
      ],
      config: {
        rateLimit: {
          max: 10,
          timeWindow: "1 minute",
        },
      },
    },
    async (request, reply) => {
      const { id } = request.params as { id: string };
      const userId = request.userId;
      const project = await db.query.projects.findFirst({
        where: eq(projects.id, id),
      });
      if (!project) {
        return sendError(reply, 404, "Not found", "NOT_FOUND");
      }
      if (project.userId !== userId) {
        return sendError(reply, 403, "Forbidden", "FORBIDDEN");
      }

      const body = request.validatedBody as { prompt: string };

      // Gather assets for context
      const projectAssets = await db.query.assets.findMany({
        where: eq(assets.projectId, id),
      });

      let currentCutList = project.cutList;
      if (!currentCutList) {
        currentCutList = buildInitialCutList(projectAssets || []);
        await db
          .update(projects)
          .set({ cutList: currentCutList, updatedAt: new Date() })
          .where(eq(projects.id, id));
      }

      try {
        const result = await applyPromptEdit({
          userId,
          prompt: body.prompt,
          cutList: currentCutList,
          assets: (projectAssets || []).map((a) => ({
            id: a.id,
            type: a.type,
            filename: a.filename,
            durationSec: a.durationSec,
          })),
        });

        // Track token usage
        const provider = (process.env.AI_PROVIDER ?? "claude").split(",")[0]?.trim() || "claude";
        await incrementTokenUsage(userId, result.usage.totalTokens, provider, "/api/projects/:id/prompt");

        // Save the new cutlist
        const [updated] = await db
          .update(projects)
          .set({
            cutList: result.newCutList,
            updatedAt: new Date(),
          })
          .where(eq(projects.id, id))
          .returning();

        await cacheDel(`projects:list:${userId}`);

        return {
          project: updated,
          diff: result.diff,
          explanation: result.explanation,
          usage: result.usage,
        };
      } catch (err) {
        request.log.error({ err }, "Prompt edit failed");
        const rawCode =
          err && typeof err === "object" && "code" in err ? (err as { code?: string }).code : undefined;
        const code: ApiErrorCode = isApiErrorCode(rawCode) ? rawCode : "INTERNAL_ERROR";
        const status = code === "PROVIDER_KEY_MISSING" ? 400 : code === "ALL_PROVIDERS_FAILED" ? 503 : 500;
        const details =
          err && typeof err === "object" && "details" in err
            ? (err as { details?: unknown }).details
            : undefined;
        if (err instanceof Error) {
          const message = err.message || "AI edit failed";
          return sendError(reply, status, message, code, details);
        }
        return sendError(reply, status, "AI edit failed", code, details);
      }
    },
  );

  // Delete project
  app.delete("/:id", async (request, reply) => {
    const { id } = request.params as { id: string };
    const userId = request.userId;
    if (!userId) {
      return sendError(reply, 401, "Unauthorized", "UNAUTHORIZED");
    }
    const project = await db.query.projects.findFirst({
      where: eq(projects.id, id),
    });
    if (!project) {
      return sendError(reply, 404, "Not found", "NOT_FOUND");
    }
    if (project.userId !== userId) {
      return sendError(reply, 403, "Forbidden", "FORBIDDEN");
    }

    // Clean up assets from R2 before deleting the DB row. If storage cleanup
    // fails, the project remains intact so the user/admin can retry.
    try {
      await deleteProjectAssets(id);
    } catch (err) {
      request.log.error({ err, projectId: id }, "Failed to delete project assets from storage");
      return sendError(reply, 500, "Failed to delete project assets", "STORAGE_ERROR");
    }

    await db.delete(projects).where(eq(projects.id, id));
    await cacheDel(`projects:list:${userId}`);
    return { success: true };
  });
}
