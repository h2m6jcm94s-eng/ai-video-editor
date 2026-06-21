// Copyright (c) 2025 Devayan Dewri. All rights reserved.
import type { ApiErrorCode } from "@ai-video-editor/shared-types";
import { and, desc, eq, inArray } from "drizzle-orm";
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { FastifyInstance } from "fastify";
import { z } from "zod";
import { db } from "../db";
import { projects, renders } from "../db/schema";
import { createCompletionToken, verifyCompletionToken } from "../lib/crypto";
import { sendError } from "../lib/errors";
import { rendersTotal, syncRendersActiveGauge } from "../lib/metrics";
import { requireInternalToken } from "../middleware/requireInternalToken";
import { createRenderSchema, renderOptionsSchema, validateBody } from "../middleware/validate";
import { enqueueJob } from "../services/queue";
import { startRenderWorkflow } from "../services/temporal";

const completeRenderSchema = z
  .object({
    status: z.enum(["complete", "failed"]),
    outputAssetId: z.string().uuid().optional(),
    previewAssetId: z.string().uuid().optional(),
    errorMessage: z.string().max(2000).optional(),
    completionToken: z.string().min(1),
  })
  .refine((data) => data.status !== "complete" || !!data.outputAssetId, {
    message: "outputAssetId is required when status is complete",
    path: ["outputAssetId"],
  });

type StartRenderResult =
  | { ok: true; job: typeof renders.$inferSelect; project: typeof projects.$inferSelect }
  | { ok: false; status: number; message: string; code: string; extra?: Record<string, unknown> };

async function startRenderAtomic(
  projectId: string,
  userId: string,
  options?: Record<string, unknown>,
): Promise<StartRenderResult> {
  const values = {
    projectId,
    status: "queued" as const,
    stage: "queued" as const,
    progress: 0,
    options: options || null,
    startedAt: new Date(),
  };

  // Use a real DB transaction when available (production). In test environments
  // the mocked db may not expose `.transaction`, so fall back to the same logic
  // without a row lock.
  if (typeof db.transaction === "function") {
    return db.transaction(async (tx): Promise<StartRenderResult> => {
      const [project] = await tx.select().from(projects).where(eq(projects.id, projectId)).for("update");
      if (!project) {
        return { ok: false, status: 404, message: "Project not found", code: "NOT_FOUND" };
      }
      if (project.userId !== userId) {
        return { ok: false, status: 403, message: "Forbidden", code: "FORBIDDEN" };
      }
      if (!project.songAssetId) {
        return { ok: false, status: 422, message: "Project missing song asset", code: "MISSING_ASSETS" };
      }

      const existing = await tx.query.renders.findFirst({
        where: and(eq(renders.projectId, projectId), inArray(renders.status, ["queued", "running"])),
      });
      if (existing) {
        return {
          ok: false,
          status: 409,
          message: "Render already in progress",
          code: "RENDER_ALREADY_RUNNING",
          extra: { jobId: existing.id },
        };
      }

      const [job] = await tx.insert(renders).values(values).returning();
      return { ok: true, job, project };
    });
  }

  const project = await db.query.projects.findFirst({
    where: eq(projects.id, projectId),
  });
  if (!project) {
    return { ok: false, status: 404, message: "Project not found", code: "NOT_FOUND" };
  }
  if (project.userId !== userId) {
    return { ok: false, status: 403, message: "Forbidden", code: "FORBIDDEN" };
  }
  if (!project.songAssetId) {
    return { ok: false, status: 422, message: "Project missing song asset", code: "MISSING_ASSETS" };
  }

  const existing = await db.query.renders.findFirst({
    where: and(eq(renders.projectId, projectId), inArray(renders.status, ["queued", "running"])),
  });
  if (existing) {
    return {
      ok: false,
      status: 409,
      message: "Render already in progress",
      code: "RENDER_ALREADY_RUNNING",
      extra: { jobId: existing.id },
    };
  }

  const [job] = await db.insert(renders).values(values).returning();
  return { ok: true, job, project };
}

export async function renderRoutes(app: FastifyInstance) {
  // Start render
  app.post(
    "/",
    {
      preHandler: validateBody(createRenderSchema),
      config: {
        rateLimit: {
          max: 3,
          timeWindow: "1 minute",
        },
      },
    },
    async (request, reply) => {
      const body = request.validatedBody as z.infer<typeof createRenderSchema>;
      const userId = request.userId;

      let renderOptions: Record<string, unknown> | undefined;
      if (body.options) {
        const parsed = renderOptionsSchema.safeParse(body.options);
        if (!parsed.success) {
          return sendError(reply, 422, "Invalid render options", "VALIDATION_ERROR", parsed.error.format());
        }
        renderOptions = parsed.data;
      }

      const startResult = await startRenderAtomic(body.projectId, userId, renderOptions);
      if (!startResult.ok) {
        return sendError(
          reply,
          startResult.status,
          startResult.message,
          startResult.code as ApiErrorCode,
          startResult.extra,
        );
      }

      const { job, project } = startResult;
      const completionToken = createCompletionToken(job.id, project.id);

      // Fetch storage keys for all assets used in the render
      const assetIds = [
        project.referenceAssetId,
        project.songAssetId,
        ...((project.clipAssetIds as string[]) || []),
      ].filter((id): id is string => Boolean(id));

      const assetRows =
        (assetIds.length
          ? await db.query.assets.findMany({
              where: (table, { inArray }) => inArray(table.id, assetIds),
              columns: { id: true, storageKey: true, metadata: true },
            })
          : []) ?? [];

      // Collect segmentation masks from any project asset (reference or clips).
      // For each source asset we keep the first mask so the compiler knows which
      // matte belongs to which slot.
      const maskSourceMap: Record<string, string> = {};
      const maskAssetIds: string[] = [];
      for (const row of assetRows) {
        const metadata = (row.metadata as Record<string, unknown> | null) ?? {};
        const segmentation = (metadata.segmentation as Record<string, unknown> | null) ?? {};
        const ids = (segmentation.maskAssetIds as string[] | undefined) ?? [];
        if (ids.length > 0) {
          maskSourceMap[row.id] = ids[0];
          maskAssetIds.push(...ids);
        }
      }

      const maskRows =
        (maskAssetIds.length
          ? await db.query.assets.findMany({
              where: (table, { inArray }) => inArray(table.id, maskAssetIds),
              columns: { id: true, storageKey: true },
            })
          : []) ?? [];

      const assetKeyMap: Record<string, string> = {};
      for (const row of [...assetRows, ...maskRows]) {
        if (row?.id && row?.storageKey) {
          assetKeyMap[row.id] = row.storageKey;
        }
      }

      // Start Temporal workflow
      let workflowId: string;
      try {
        workflowId = await startRenderWorkflow({
          projectId: project.id,
          referenceAssetId: project.referenceAssetId ?? undefined,
          songAssetId: project.songAssetId!,
          clipAssetIds: (project.clipAssetIds as string[]) || [],
          styleTier: project.styleTier,
          mode: project.mode,
          userId,
          renderId: job.id,
          completionToken,
          assetKeyMap,
          styleAnalysis: (project.styleAnalysis as Record<string, unknown>) ?? undefined,
          maskAssetIds,
          maskSourceMap,
        });
      } catch (e) {
        // Mark render as failed and return 500 without crashing
        const errorMessage = e instanceof Error ? e.message : String(e);
        await db.update(renders).set({ status: "failed", errorMessage }).where(eq(renders.id, job.id));
        return sendError(reply, 500, "Render engine unavailable", "TEMPORAL_ERROR");
      }

      await db.update(renders).set({ workflowId }).where(eq(renders.id, job.id));

      // Enqueue to Redis/Temporal
      await enqueueJob({
        jobId: job.id,
        projectId: body.projectId,
        type: "video_render",
        payload: body.options || {},
        priority: 1,
        createdAt: new Date().toISOString(),
      });

      // Only count renders that successfully entered the workflow engine.
      // If Temporal failed above, the render row is marked failed and the gauge is untouched.
      rendersTotal.inc({ status: "started" });
      await syncRendersActiveGauge();

      // Update project status
      await db
        .update(projects)
        .set({ status: "rendering", updatedAt: new Date() })
        .where(eq(projects.id, body.projectId));

      return { job: { ...job, workflowId } };
    },
  );

  // Get render job
  app.get("/:jobId", async (request, reply) => {
    const { jobId } = request.params as { jobId: string };
    const userId = request.userId;

    const job = await db.query.renders.findFirst({
      where: eq(renders.id, jobId),
      with: { project: true },
    });

    if (!job) {
      return sendError(reply, 404, "Job not found", "NOT_FOUND");
    }

    if (!job.project || job.project.userId !== userId) {
      return sendError(reply, 403, "Forbidden", "FORBIDDEN");
    }

    return { job };
  });

  // List renders for project
  app.get("/project/:projectId", async (request, reply) => {
    const { projectId } = request.params as { projectId: string };
    const userId = request.userId;

    const project = await db.query.projects.findFirst({
      where: eq(projects.id, projectId),
    });
    if (!project || project.userId !== userId) {
      return sendError(reply, 403, "Forbidden", "FORBIDDEN");
    }

    const projectRenders = await db.query.renders.findMany({
      where: eq(renders.projectId, projectId),
      orderBy: [desc(renders.createdAt)],
    });
    return { jobs: projectRenders };
  });

  // Worker webhook: mark render complete/failed
  app.post(
    "/:jobId/complete",
    { preHandler: [requireInternalToken, validateBody(completeRenderSchema)] },
    async (request, reply) => {
      const { jobId } = request.params as { jobId: string };
      const body = request.validatedBody as z.infer<typeof completeRenderSchema>;

      const job = await db.query.renders.findFirst({ where: eq(renders.id, jobId) });
      if (!job) {
        return sendError(reply, 404, "Job not found", "NOT_FOUND");
      }

      // Sanity-check that the render belongs to a real project before mutating status.
      const project = await db.query.projects.findFirst({
        where: eq(projects.id, job.projectId),
      });
      if (!project) {
        return sendError(reply, 404, "Project not found", "NOT_FOUND");
      }

      // Verify the render-scoped completion token so a leaked global internal token
      // cannot mutate arbitrary renders.
      if (!verifyCompletionToken(body.completionToken, jobId, job.projectId)) {
        return sendError(reply, 403, "Invalid completion token", "FORBIDDEN");
      }

      const [updated] = await db
        .update(renders)
        .set({
          status: body.status,
          outputAssetId: body.outputAssetId ?? null,
          previewAssetId: body.previewAssetId ?? null,
          errorMessage: body.errorMessage ?? null,
          completedAt: new Date(),
        })
        .where(eq(renders.id, jobId))
        .returning();

      if (body.status === "complete") {
        rendersTotal.inc({ status: "complete" });
        await db
          .update(projects)
          .set({ status: "complete", updatedAt: new Date(), renderAssetId: body.outputAssetId ?? null })
          .where(eq(projects.id, job.projectId));
      } else {
        rendersTotal.inc({ status: "failed" });
        await db
          .update(projects)
          .set({ status: "failed", updatedAt: new Date() })
          .where(eq(projects.id, job.projectId));
      }

      await syncRendersActiveGauge();

      return { job: updated };
    },
  );
}
