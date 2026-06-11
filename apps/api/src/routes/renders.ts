// Copyright (c) 2025 Devayan Dewri. All rights reserved.
import { and, desc, eq, inArray } from "drizzle-orm";
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { FastifyInstance } from "fastify";
import { z } from "zod";
import { db } from "../db";
import { assets, projects, renders } from "../db/schema";
import { sendError } from "../lib/errors";
import { rendersActive, rendersTotal } from "../lib/metrics";
import { requireInternalToken } from "../middleware/requireInternalToken";
import { createRenderSchema, validateBody } from "../middleware/validate";
import { enqueueJob } from "../services/queue";
import { startRenderWorkflow } from "../services/temporal";

const completeRenderSchema = z.object({
  status: z.enum(["complete", "failed"]),
  outputAssetId: z.string().uuid().optional(),
  previewAssetId: z.string().uuid().optional(),
  errorMessage: z.string().max(2000).optional(),
});

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

      // Validate project exists and user owns it
      const project = await db.query.projects.findFirst({
        where: eq(projects.id, body.projectId),
      });
      if (!project) {
        return sendError(reply, 404, "Project not found", "NOT_FOUND");
      }
      if (project.userId !== userId) {
        return sendError(reply, 403, "Forbidden", "FORBIDDEN");
      }

      // Validate project has required assets
      if (!project.referenceAssetId || !project.songAssetId) {
        return sendError(reply, 422, "Project missing reference asset or song", "MISSING_ASSETS");
      }

      // Idempotency: prevent duplicate in-progress renders
      const existing = await db.query.renders.findFirst({
        where: and(eq(renders.projectId, body.projectId), inArray(renders.status, ["queued", "running"])),
      });
      if (existing) {
        return sendError(reply, 409, "Render already in progress", "RENDER_ALREADY_RUNNING", {
          jobId: existing.id,
        });
      }

      const [job] = await db
        .insert(renders)
        .values({
          projectId: body.projectId,
          status: "queued",
          stage: "queued",
          progress: 0,
          startedAt: new Date(),
        })
        .returning();

      // Fetch storage keys for all assets used in the render
      const assetIds = [
        project.referenceAssetId,
        project.songAssetId,
        ...((project.clipAssetIds as string[]) || []),
      ].filter(Boolean) as string[];

      const assetRows = assetIds.length
        ? await db.query.assets.findMany({
            where: (table, { inArray }) => inArray(table.id, assetIds),
            columns: { id: true, storageKey: true },
          })
        : [];

      const assetKeyMap: Record<string, string> = {};
      for (const row of assetRows ?? []) {
        if (row?.id && row?.storageKey) {
          assetKeyMap[row.id] = row.storageKey;
        }
      }

      // Start Temporal workflow
      let workflowId: string;
      try {
        workflowId = await startRenderWorkflow({
          projectId: project.id,
          referenceAssetId: project.referenceAssetId,
          songAssetId: project.songAssetId,
          clipAssetIds: (project.clipAssetIds as string[]) || [],
          styleTier: project.styleTier,
          mode: project.mode,
          userId,
          renderId: job.id,
          assetKeyMap,
        });
      } catch (e) {
        // Mark render as failed and return 500 without crashing
        await db
          .update(renders)
          .set({ status: "failed", errorMessage: "Temporal workflow failed" })
          .where(eq(renders.id, job.id));
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

      rendersActive.inc();
      rendersTotal.inc({ status: "started" });

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
    { preHandler: [validateBody(completeRenderSchema), requireInternalToken] },
    async (request, reply) => {
      const { jobId } = request.params as { jobId: string };
      const body = request.validatedBody as z.infer<typeof completeRenderSchema>;

      const job = await db.query.renders.findFirst({ where: eq(renders.id, jobId) });
      if (!job) {
        return sendError(reply, 404, "Job not found", "NOT_FOUND");
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
        rendersActive.dec();
        rendersTotal.inc({ status: "complete" });
        await db
          .update(projects)
          .set({ status: "complete", updatedAt: new Date(), renderAssetId: body.outputAssetId ?? null })
          .where(eq(projects.id, job.projectId));
      } else {
        rendersActive.dec();
        rendersTotal.inc({ status: "failed" });
        await db
          .update(projects)
          .set({ status: "failed", updatedAt: new Date() })
          .where(eq(projects.id, job.projectId));
      }

      return { job: updated };
    },
  );
}
