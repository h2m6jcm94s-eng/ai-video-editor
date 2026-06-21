// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
/**
 * Internal routes for worker → API communication.
 * Protected by requireInternalToken.
 */

import { cutListSchema } from "@ai-video-editor/shared-types";
import { and, eq, inArray } from "drizzle-orm";
import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { db } from "../db";
import { assets, generationJobs, projects, renders } from "../db/schema";
import { verifyCompletionToken } from "../lib/crypto";
import { sendError } from "../lib/errors";
import { recordUserEvent } from "../lib/userEvents";
import { requireInternalToken } from "../middleware/requireInternalToken";
import { validateBody } from "../middleware/validate";
import { publishProgress, setJobStatus } from "../services/queue";

const userEventSchema = z
  .object({
    userId: z.string().uuid(),
    code: z.string().min(1).max(50),
    message: z.string().min(1).max(2000),
    details: z.record(z.unknown()).optional(),
    route: z.string().max(255).optional(),
  })
  .strict();

const createAssetSchema = z
  .object({
    projectId: z.string().uuid(),
    type: z.enum(["reference_video", "song", "clip", "render", "subtitle", "lut", "sfx", "mask"]),
    filename: z
      .string()
      .min(1)
      .max(255)
      .regex(/^[^/\\\\]+$/, "Filename cannot contain path separators"),
    mimeType: z.string().min(1).max(100),
  })
  .strict();

const probeUpdateSchema = z
  .object({
    durationSec: z.number().min(0).max(86400).optional(),
    width: z.number().int().min(1).max(7680).optional(),
    height: z.number().int().min(1).max(7680).optional(),
    fps: z.number().min(1).max(120).optional(),
  })
  .strict();

const assetCompleteSchema = z
  .object({
    sizeBytes: z
      .number()
      .int()
      .min(0)
      .max(5 * 1024 * 1024 * 1024),
    storageUrl: z.string().url().optional(),
    metadata: z.record(z.unknown()).optional(),
  })
  .strict();

const metadataPatchSchema = z
  .object({
    metadata: z
      .record(z.unknown())
      .refine((val) => JSON.stringify(val).length <= 65536, {
        message: "Metadata payload too large",
      })
      .refine((val) => Object.keys(val).length <= 100, {
        message: "Metadata has too many keys",
      }),
  })
  .strict();

export async function internalRoutes(app: FastifyInstance) {
  app.addHook("preHandler", requireInternalToken);

  app.post("/api/internal/user-events", async (request, reply) => {
    const parsed = userEventSchema.safeParse(request.body);
    if (!parsed.success) {
      return sendError(reply, 422, "Invalid user event payload", "VALIDATION_ERROR", parsed.error.format());
    }
    await recordUserEvent(parsed.data);
    return { ok: true };
  });

  // Get project details (including cut-list and asset IDs) for render worker
  app.get("/api/internal/projects/:id", async (request, reply) => {
    const { id } = request.params as { id: string };

    const project = await db.query.projects.findFirst({
      where: eq(projects.id, id),
      with: { assets: true },
    });

    if (!project) {
      return sendError(reply, 404, "Project not found", "NOT_FOUND");
    }

    const activeRender = await db.query.renders.findFirst({
      where: and(eq(renders.projectId, id), inArray(renders.status, ["queued", "running"])),
      orderBy: (renders, { desc }) => [desc(renders.createdAt)],
    });

    return {
      project: {
        id: project.id,
        userId: project.userId,
        name: project.name,
        status: project.status,
        styleTier: project.styleTier,
        mode: project.mode,
        referenceAssetId: project.referenceAssetId,
        songAssetId: project.songAssetId,
        clipAssetIds: project.clipAssetIds,
        cutList: project.cutList,
        renderAssetId: project.renderAssetId,
        createdAt: project.createdAt,
        updatedAt: project.updatedAt,
      },
      assets: project.assets.map((a) => ({
        id: a.id,
        projectId: a.projectId,
        type: a.type,
        filename: a.filename,
        mimeType: a.mimeType,
        sizeBytes: a.sizeBytes,
        durationSec: a.durationSec,
        width: a.width,
        height: a.height,
        fps: a.fps,
        storageKey: a.storageKey,
        storageUrl: a.storageUrl,
        metadata: a.metadata,
      })),
      activeRender: activeRender
        ? {
            id: activeRender.id,
            status: activeRender.status,
            stage: activeRender.stage,
            progress: activeRender.progress,
            workflowId: activeRender.workflowId,
            options: activeRender.options,
          }
        : null,
    };
  });

  // Create a new asset row for worker-generated outputs (e.g. renders, LUTs)
  app.post(
    "/api/internal/assets",
    { preHandler: [requireInternalToken, validateBody(createAssetSchema)] },
    async (request, reply) => {
      const body = request.validatedBody as z.infer<typeof createAssetSchema>;

      const project = await db.query.projects.findFirst({
        where: eq(projects.id, body.projectId),
      });
      if (!project) {
        return sendError(reply, 404, "Project not found", "NOT_FOUND");
      }

      const assetId = crypto.randomUUID();
      const key = `projects/${body.projectId}/${body.type}/${assetId}-${body.filename}`;

      const [asset] = await db
        .insert(assets)
        .values({
          id: assetId,
          projectId: body.projectId,
          type: body.type,
          filename: body.filename,
          mimeType: body.mimeType,
          sizeBytes: 0,
          storageKey: key,
          storageUrl: "",
        })
        .returning();

      return { assetId: asset.id, storageKey: asset.storageKey, asset };
    },
  );

  // Update asset probe metadata (used by ingest worker after ffprobe)
  app.patch(
    "/api/internal/assets/:assetId/probe",
    { preHandler: [requireInternalToken, validateBody(probeUpdateSchema)] },
    async (request, reply) => {
      const { assetId } = request.params as { assetId: string };
      const body = request.validatedBody as z.infer<typeof probeUpdateSchema>;

      const asset = await db.query.assets.findFirst({
        where: eq(assets.id, assetId),
      });
      if (!asset) {
        return sendError(reply, 404, "Asset not found", "NOT_FOUND");
      }

      const [updated] = await db
        .update(assets)
        .set({
          durationSec: body.durationSec,
          width: body.width,
          height: body.height,
          fps: body.fps,
        })
        .where(eq(assets.id, assetId))
        .returning();

      return { asset: updated };
    },
  );

  // Merge metadata into an existing asset (used by workers for segmentation, etc.)
  app.patch(
    "/api/internal/assets/:assetId/metadata",
    {
      preHandler: [requireInternalToken, validateBody(metadataPatchSchema)],
      bodyLimit: 256 * 1024,
    },
    async (request, reply) => {
      const { assetId } = request.params as { assetId: string };
      const body = request.validatedBody as z.infer<typeof metadataPatchSchema>;

      const asset = await db.query.assets.findFirst({
        where: eq(assets.id, assetId),
      });
      if (!asset) {
        return sendError(reply, 404, "Asset not found", "NOT_FOUND");
      }

      const merged = { ...(asset.metadata || {}), ...(body.metadata || {}) };
      const [updated] = await db
        .update(assets)
        .set({ metadata: merged })
        .where(eq(assets.id, assetId))
        .returning();

      return { asset: updated };
    },
  );

  // Mark a worker-generated asset as complete and set its public URL
  app.patch(
    "/api/internal/assets/:assetId/complete",
    { preHandler: [requireInternalToken, validateBody(assetCompleteSchema)] },
    async (request, reply) => {
      const { assetId } = request.params as { assetId: string };
      const body = request.validatedBody as z.infer<typeof assetCompleteSchema>;

      const asset = await db.query.assets.findFirst({
        where: eq(assets.id, assetId),
      });
      if (!asset) {
        return sendError(reply, 404, "Asset not found", "NOT_FOUND");
      }

      const [updated] = await db
        .update(assets)
        .set({
          sizeBytes: body.sizeBytes,
          storageUrl: body.storageUrl ?? asset.storageUrl,
          metadata: body.metadata ?? asset.metadata,
        })
        .where(eq(assets.id, assetId))
        .returning();

      return { asset: updated };
    },
  );

  // Publish a progress event for any job (render or generation)
  const progressPublishSchema = z
    .object({
      stage: z.string().min(1).max(100),
      progress: z.number().min(0).max(100),
      message: z.string().max(2000).optional(),
    })
    .strict();

  app.post(
    "/api/internal/progress/:jobId",
    { preHandler: [requireInternalToken, validateBody(progressPublishSchema)] },
    async (request, reply) => {
      const { jobId } = request.params as { jobId: string };
      const body = request.validatedBody as z.infer<typeof progressPublishSchema>;

      const renderJob = await db.query.renders.findFirst({ where: eq(renders.id, jobId) });
      const generationJob = renderJob
        ? null
        : await db.query.generationJobs.findFirst({ where: eq(generationJobs.id, jobId) });
      if (!renderJob && !generationJob) {
        return sendError(reply, 404, "Job not found", "NOT_FOUND");
      }

      await Promise.all([
        publishProgress(jobId, body.stage, body.progress, body.message || ""),
        setJobStatus(jobId, body.stage, body.progress, body.message || ""),
      ]);

      if (renderJob) {
        await db
          .update(renders)
          .set({ stage: body.stage, progress: body.progress })
          .where(eq(renders.id, jobId));
      } else {
        await db
          .update(generationJobs)
          .set({ stage: body.stage, progress: body.progress })
          .where(eq(generationJobs.id, jobId));
      }

      return { ok: true };
    },
  );

  // Persist a generated cut-list and mark the generation job complete
  const generatedCutlistSchema = z
    .object({
      cutList: cutListSchema,
      generationJobId: z.string().uuid(),
      completionToken: z.string().min(1).optional(),
    })
    .strict();

  app.patch(
    "/api/internal/projects/:id/generated-cutlist",
    { preHandler: [requireInternalToken, validateBody(generatedCutlistSchema)] },
    async (request, reply) => {
      const { id } = request.params as { id: string };
      const body = request.validatedBody as z.infer<typeof generatedCutlistSchema>;

      const project = await db.query.projects.findFirst({ where: eq(projects.id, id) });
      if (!project) {
        return sendError(reply, 404, "Project not found", "NOT_FOUND");
      }

      const job = await db.query.generationJobs.findFirst({
        where: and(eq(generationJobs.id, body.generationJobId), eq(generationJobs.projectId, id)),
      });
      if (!job) {
        return sendError(reply, 404, "Generation job not found", "NOT_FOUND");
      }

      if (body.completionToken && !verifyCompletionToken(body.completionToken, job.id, id)) {
        return sendError(reply, 403, "Invalid completion token", "FORBIDDEN");
      }

      const [updatedProject] = await db
        .update(projects)
        .set({ cutList: body.cutList, updatedAt: new Date() })
        .where(eq(projects.id, id))
        .returning();

      const [updatedJob] = await db
        .update(generationJobs)
        .set({
          status: "complete",
          stage: "complete",
          progress: 100,
          outputCutList: body.cutList,
          completedAt: new Date(),
        })
        .where(eq(generationJobs.id, job.id))
        .returning();

      await publishProgress(job.id, "complete", 100, "Cut-list generation complete");
      await setJobStatus(job.id, "complete", 100, "Cut-list generation complete");

      return { project: updatedProject, job: updatedJob };
    },
  );

  // Mark a generation job as failed
  const failGenerationSchema = z
    .object({
      errorMessage: z.string().min(1).max(2000),
      completionToken: z.string().min(1).optional(),
    })
    .strict();

  app.post(
    "/api/internal/generation-jobs/:jobId/fail",
    { preHandler: [requireInternalToken, validateBody(failGenerationSchema)] },
    async (request, reply) => {
      const { jobId } = request.params as { jobId: string };
      const body = request.validatedBody as z.infer<typeof failGenerationSchema>;

      const job = await db.query.generationJobs.findFirst({ where: eq(generationJobs.id, jobId) });
      if (!job) {
        return sendError(reply, 404, "Generation job not found", "NOT_FOUND");
      }

      if (body.completionToken && !verifyCompletionToken(body.completionToken, jobId, job.projectId)) {
        return sendError(reply, 403, "Invalid completion token", "FORBIDDEN");
      }

      const [updated] = await db
        .update(generationJobs)
        .set({
          status: "failed",
          stage: "failed",
          progress: 0,
          errorMessage: body.errorMessage,
          completedAt: new Date(),
        })
        .where(eq(generationJobs.id, jobId))
        .returning();

      await publishProgress(jobId, "failed", 0, body.errorMessage);
      await setJobStatus(jobId, "failed", 0, body.errorMessage);

      return { job: updated };
    },
  );
}
