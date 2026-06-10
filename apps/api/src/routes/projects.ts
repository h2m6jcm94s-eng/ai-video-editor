// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { FastifyInstance } from "fastify";
import { eq, desc, and, inArray } from "drizzle-orm";
import { db } from "../db";
import { projects, assets, renders } from "../db/schema";
import type { ProjectStatus, StyleTier, EditMode } from "@ai-video-editor/shared-types";
import { sendCutlistApprovedSignal, startRenderWorkflow } from "../services/temporal";
import { deleteProjectAssets, downloadAsset } from "../services/storage";
import { validateBody, createProjectSchema, patchProjectSchema, updateCutlistSchema, promptEditSchema } from "../middleware/validate";
import { applyPromptEdit, transcribeAudio } from "../services/ai";
import { sendError } from "../lib/errors";
import { API_ERROR_CODES } from "@ai-video-editor/shared-types";
import { cacheGet, cacheSet, cacheDel } from "../lib/cache";
import { validatePromptGuardrails } from "../middleware/guardrails";
import { enforceTokenBudget, incrementTokenUsage, getUsageForUser } from "../middleware/tokenBudget";
import fs from "fs";
import path from "path";
import os from "os";

export async function projectRoutes(app: FastifyInstance) {
  // List projects for user
  app.get("/", async (request, reply) => {
    const userId = request.userId;
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

    const [project] = await db
      .insert(projects)
      .values({
        name: body.name || "Untitled Project",
        status: "uploading",
        userId,
        styleTier: body.styleTier || "full_style",
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
    const project = await db.query.projects.findFirst({
      where: eq(projects.id, id),
    });
    if (!project) {
      return sendError(reply, 404, "Not found", "NOT_FOUND");
    }
    if (project.userId !== userId) {
      return sendError(reply, 403, "Forbidden", "FORBIDDEN");
    }

    const body = request.validatedBody as { cutList: any };
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

    return { project: updated };
  });

  // Transcribe audio asset to subtitles
  app.post("/:id/transcribe", {
    preHandler: validatePromptGuardrails,
    config: {
      rateLimit: {
        max: 5,
        timeWindow: "1 minute",
      },
    },
  }, async (request, reply) => {
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
        err && typeof err === "object" && "code" in err
          ? (err as { code?: string }).code
          : undefined;
      const code = rawCode && API_ERROR_CODES.includes(rawCode as any)
        ? (rawCode as (typeof API_ERROR_CODES)[number])
        : "INTERNAL_ERROR";
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
  });

  // Prompt-to-edit (AI powered)
  app.post("/:id/prompt", {
    preHandler: [validateBody(promptEditSchema), validatePromptGuardrails, enforceTokenBudget],
    config: {
      rateLimit: {
        max: 10,
        timeWindow: "1 minute",
      },
    },
  }, async (request, reply) => {
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
    if (!project.cutList) {
      return sendError(reply, 400, "No cutlist to edit", "NO_CUTLIST");
    }

    // Gather assets for context
    const projectAssets = await db.query.assets.findMany({
      where: eq(assets.projectId, id),
    });

    try {
      const result = await applyPromptEdit({
        userId,
        prompt: body.prompt,
        cutList: project.cutList,
        assets: (projectAssets || []).map((a) => ({
          id: a.id,
          type: a.type,
          filename: a.filename,
          durationSec: a.durationSec,
        })),
      });

      // Track token usage
      const provider = process.env.AI_PROVIDER?.split(",")[0]?.trim() || "claude";
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

      return {
        project: updated,
        diff: result.diff,
        explanation: result.explanation,
        usage: result.usage,
      };
    } catch (err) {
      request.log.error({ err }, "Prompt edit failed");
      const rawCode =
        err && typeof err === "object" && "code" in err
          ? (err as { code?: string }).code
          : undefined;
      const code = rawCode && API_ERROR_CODES.includes(rawCode as any)
        ? (rawCode as (typeof API_ERROR_CODES)[number])
        : "INTERNAL_ERROR";
      const status = code === "PROVIDER_KEY_MISSING" ? 400 : 500;
      if (err instanceof Error) {
        const message = err.message || "AI edit failed";
        return sendError(reply, status, message, code);
      }
      return sendError(reply, status, "AI edit failed", code);
    }
  });

  // Delete project
  app.delete("/:id", async (request, reply) => {
    const { id } = request.params as { id: string };
    const userId = request.userId;
    const project = await db.query.projects.findFirst({
      where: eq(projects.id, id),
    });
    if (!project) {
      return reply.status(404).send({ error: "Not found", code: "NOT_FOUND" });
    }
    if (project.userId !== userId) {
      return reply.status(403).send({ error: "Forbidden", code: "FORBIDDEN" });
    }

    // Clean up assets from R2 asynchronously (don't block response)
    deleteProjectAssets(id).catch((err) => {
      request.log.error({ err, projectId: id }, "Failed to delete assets for project");
    });

    await db.delete(projects).where(eq(projects.id, id));
    await cacheDel(`projects:list:${userId}`);
    return { success: true };
  });
}
