// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
/**
 * Internal routes for worker → API communication.
 * Protected by requireInternalToken.
 */

import { cutListSchema } from "@ai-video-editor/shared-types";
import { and, count, eq, gte, inArray, ne, or, sql } from "drizzle-orm";
import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { db } from "../db";
import {
  assets,
  behaviorCorpusEntries,
  generationJobs,
  projects,
  renderBehavior,
  renderOutcomes,
  renderSignals,
  renders,
  userTasteProfiles,
} from "../db/schema";
import { canUserContribute, isAnomalousCorpusEntry, WEEKLY_CONTRIBUTION_CAP } from "../lib/behaviorCorpus";
import { verifyCompletionToken } from "../lib/crypto";
import { sendError } from "../lib/errors";
import { recordUserEvent } from "../lib/userEvents";
import { requireInternalToken } from "../middleware/requireInternalToken";
import { validateBody } from "../middleware/validate";
import { publishProgress, setJobStatus } from "../services/queue";

const OUTCOME_FINALIZATION_DAYS = 7;
const OUTCOME_FINALIZATION_MS = OUTCOME_FINALIZATION_DAYS * 24 * 60 * 60 * 1000;

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
    storageKey: z.string().min(1).max(1024).optional(),
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

const behaviorCorpusEntrySchema = z
  .object({
    signals: z.record(z.unknown()),
    behavior: z.record(z.unknown()),
    qualityWeight: z.number().min(0).max(1),
    userId: z.string().uuid(),
    isPublic: z.boolean().default(true),
    status: z.enum(["active", "quarantined", "rejected"]).optional(),
    source: z.string().max(100).default("user_render"),
    producingPredictorVersion: z.string().max(100).optional(),
  })
  .strict();

const biasVectorSchema = z.record(z.number());

const updateBiasSchema = z
  .object({
    cluster: z.string().max(50).optional(),
    biasVector: biasVectorSchema,
    profileConfidenceDelta: z.number().min(0).max(1).default(0.05),
  })
  .strict();

const ingestToCorpusSchema = z
  .object({
    qualityWeight: z.number().min(0).max(1).default(0.5),
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
      const key = body.storageKey ?? `projects/${body.projectId}/${body.type}/${assetId}-${body.filename}`;

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

  // ── Behavior corpus ───────────────────────────────────────────────────────

  const corpusQuerySchema = z
    .object({
      userId: z.string().uuid(),
      referenceGenomeHash: z.string().max(255).optional(),
      since: z.string().datetime().optional(),
      userOnly: z.enum(["true", "false"]).default("false"),
      limit: z.coerce.number().int().min(1).max(1000).default(500),
    })
    .strict();

  app.get("/api/internal/behavior-corpus", async (request, reply) => {
    const parsed = corpusQuerySchema.safeParse(request.query);
    if (!parsed.success) {
      return sendError(reply, 422, "Invalid query", "VALIDATION_ERROR", parsed.error.format());
    }
    const { userId, since, userOnly, limit } = parsed.data;

    const publicOrUser =
      userOnly === "true"
        ? eq(behaviorCorpusEntries.userId, userId)
        : or(eq(behaviorCorpusEntries.isPublic, true), eq(behaviorCorpusEntries.userId, userId));
    const dateFilter = since ? gte(behaviorCorpusEntries.createdAt, new Date(since)) : undefined;
    // Quarantined entries are never exposed to KNN / public reads.
    const statusFilter = ne(behaviorCorpusEntries.status, "quarantined");
    const whereClause = and(publicOrUser, statusFilter, dateFilter);

    const entries = await db.query.behaviorCorpusEntries.findMany({
      where: whereClause,
      orderBy: (table, { desc }) => [desc(table.qualityWeight)],
      limit,
    });

    return { entries };
  });

  async function countUserEntriesLast7d(userId: string): Promise<number> {
    const sevenDaysAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
    const [{ value }] = await db
      .select({ value: count() })
      .from(behaviorCorpusEntries)
      .where(
        and(
          eq(behaviorCorpusEntries.userId, userId),
          gte(behaviorCorpusEntries.createdAt, sevenDaysAgo),
          inArray(behaviorCorpusEntries.status, ["active", "quarantined"]),
        ),
      );
    return value ?? 0;
  }

  async function fetchActivePublicEntries(limit = 500): Promise<Array<{ signals: Record<string, unknown> }>> {
    return db.query.behaviorCorpusEntries.findMany({
      where: and(eq(behaviorCorpusEntries.status, "active"), eq(behaviorCorpusEntries.isPublic, true)),
      orderBy: (table, { desc }) => [desc(table.qualityWeight)],
      limit,
    }) as Promise<Array<{ signals: Record<string, unknown> }>>;
  }

  app.post(
    "/api/internal/behavior-corpus",
    { preHandler: validateBody(behaviorCorpusEntrySchema) },
    async (request, reply) => {
      const body = request.validatedBody as z.infer<typeof behaviorCorpusEntrySchema>;

      // Weekly contribution cap.
      const userCount7d = await countUserEntriesLast7d(body.userId);
      if (!canUserContribute(Array.from({ length: userCount7d }))) {
        return sendError(
          reply,
          429,
          `Weekly corpus contribution cap (${WEEKLY_CONTRIBUTION_CAP}) exceeded`,
          "CORPUS_CAP_EXCEEDED",
        );
      }

      // Anomaly detection against the active public corpus.
      const activePublic = await fetchActivePublicEntries();
      const anomalous = isAnomalousCorpusEntry(body.signals, activePublic);
      const status = anomalous ? "quarantined" : (body.status ?? "active");
      const isPublic = anomalous ? false : body.isPublic;
      const source = anomalous ? "quarantined" : body.source;

      const [entry] = await db
        .insert(behaviorCorpusEntries)
        .values({
          signals: body.signals,
          behavior: body.behavior,
          qualityWeight: body.qualityWeight,
          userId: body.userId,
          isPublic,
          status,
          source,
          producingPredictorVersion: body.producingPredictorVersion,
        })
        .returning();

      return { entry };
    },
  );

  // ── User taste profiles ───────────────────────────────────────────────────

  app.get("/api/internal/user-taste-profiles/:userId", async (request, reply) => {
    const { userId } = request.params as { userId: string };

    let profile = await db.query.userTasteProfiles.findFirst({
      where: eq(userTasteProfiles.userId, userId),
    });

    if (!profile) {
      const [created] = await db.insert(userTasteProfiles).values({ userId }).returning();
      profile = created;
    }

    return { profile };
  });

  app.put(
    "/api/internal/user-taste-profiles/:userId/bias",
    { preHandler: validateBody(updateBiasSchema) },
    async (request, reply) => {
      const { userId } = request.params as { userId: string };
      const body = request.validatedBody as z.infer<typeof updateBiasSchema>;
      const cluster = body.cluster || "general";

      const existing = await db.query.userTasteProfiles.findFirst({
        where: eq(userTasteProfiles.userId, userId),
      });

      const typedClusterBiasVectors = (existing?.clusterBiasVectors ?? { general: {} }) as Record<
        string,
        Record<string, number>
      >;
      const existingCluster = typedClusterBiasVectors[cluster] ?? {};
      const merged: Record<string, number> = { ...existingCluster };
      for (const [key, value] of Object.entries(body.biasVector)) {
        merged[key] = (merged[key] || 0) + value;
      }
      const clusterBiasVectors = { ...typedClusterBiasVectors, [cluster]: merged };

      if (!existing) {
        const [created] = await db
          .insert(userTasteProfiles)
          .values({
            userId,
            clusterBiasVectors,
            profileConfidence: body.profileConfidenceDelta,
          })
          .returning();
        return { profile: created };
      }

      const [updated] = await db
        .update(userTasteProfiles)
        .set({
          clusterBiasVectors,
          profileConfidence: Math.min(1, (existing.profileConfidence || 0) + body.profileConfidenceDelta),
          lastUpdatedAt: new Date(),
        })
        .where(eq(userTasteProfiles.id, existing.id))
        .returning();

      return { profile: updated };
    },
  );

  // ── Render feedback bundle / corpus ingestion ─────────────────────────────

  app.get("/api/internal/renders/:renderId/feedback", async (request, reply) => {
    const { renderId } = request.params as { renderId: string };

    const job = await db.query.renders.findFirst({ where: eq(renders.id, renderId) });
    if (!job) {
      return sendError(reply, 404, "Render not found", "NOT_FOUND");
    }

    const signals = await db.query.renderSignals.findFirst({
      where: eq(renderSignals.renderId, renderId),
    });
    const behavior = await db.query.renderBehavior.findFirst({
      where: eq(renderBehavior.renderId, renderId),
    });

    return { signals, behavior, userId: job.userId, projectId: job.projectId };
  });

  app.post(
    "/api/internal/renders/:renderId/ingest-to-corpus",
    { preHandler: validateBody(ingestToCorpusSchema) },
    async (request, reply) => {
      const { renderId } = request.params as { renderId: string };
      const body = request.validatedBody as z.infer<typeof ingestToCorpusSchema>;

      const job = await db.query.renders.findFirst({ where: eq(renders.id, renderId) });
      if (!job) {
        return sendError(reply, 404, "Render not found", "NOT_FOUND");
      }

      const signals = await db.query.renderSignals.findFirst({
        where: eq(renderSignals.renderId, renderId),
      });
      const behavior = await db.query.renderBehavior.findFirst({
        where: eq(renderBehavior.renderId, renderId),
      });
      if (!signals || !behavior) {
        return sendError(reply, 422, "Missing signals or behavior for render", "VALIDATION_ERROR");
      }

      const project = await db.query.projects.findFirst({ where: eq(projects.id, job.projectId) });
      if (project?.excludeFromLearning) {
        return { ok: true, excluded: true, reason: "project excluded from learning" };
      }

      // Outcomes are provisional until the 7-day labeling window closes.
      let outcome = await db.query.renderOutcomes.findFirst({
        where: eq(renderOutcomes.renderId, renderId),
      });
      const completedAt = job.completedAt ? new Date(job.completedAt).getTime() : Date.now();
      const windowClosed = Date.now() - completedAt >= OUTCOME_FINALIZATION_MS;

      if (!outcome?.isFinalized) {
        if (!windowClosed) {
          return sendError(
            reply,
            425,
            `Outcome labeling window still open; finalize after ${OUTCOME_FINALIZATION_DAYS} days`,
            "OUTCOME_WINDOW_OPEN",
          );
        }

        const now = new Date();
        await db
          .insert(renderOutcomes)
          .values({
            renderId,
            userId: job.userId,
            projectId: job.projectId,
            isFinalized: true,
            finalizedAt: now,
            updatedAt: now,
          })
          .onConflictDoUpdate({
            target: renderOutcomes.renderId,
            set: { isFinalized: true, finalizedAt: now, updatedAt: now },
          });
        outcome = {
          ...(outcome ?? {}),
          isFinalized: true,
          finalizedAt: now,
        } as typeof renderOutcomes.$inferSelect;
      }

      // Weekly contribution cap.
      const userCount7d = await countUserEntriesLast7d(job.userId);
      if (!canUserContribute(Array.from({ length: userCount7d }))) {
        return sendError(
          reply,
          429,
          `Weekly corpus contribution cap (${WEEKLY_CONTRIBUTION_CAP}) exceeded`,
          "CORPUS_CAP_EXCEEDED",
        );
      }

      let profile = await db.query.userTasteProfiles.findFirst({
        where: eq(userTasteProfiles.userId, job.userId),
      });
      if (!profile) {
        const [created] = await db.insert(userTasteProfiles).values({ userId: job.userId }).returning();
        profile = created;
      }

      // Anomaly detection against the active public corpus.
      const activePublic = await fetchActivePublicEntries();
      const anomalous = isAnomalousCorpusEntry(signals as Record<string, unknown>, activePublic);

      const contribute = profile.contributeToGlobalCorpus ?? true;
      const status = anomalous ? "quarantined" : "active";
      const isPublic = anomalous ? false : contribute;
      const source = anomalous ? "quarantined" : "user_render";

      const [entry] = await db
        .insert(behaviorCorpusEntries)
        .values({
          signals: signals as Record<string, unknown>,
          behavior: behavior as Record<string, unknown>,
          qualityWeight: body.qualityWeight,
          userId: job.userId,
          isPublic,
          status,
          source,
          producingPredictorVersion: behavior.predictorVersion ?? undefined,
        })
        .returning();

      return { ok: true, entry };
    },
  );
}
