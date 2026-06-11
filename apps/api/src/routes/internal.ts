// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
/**
 * Internal routes for worker → API communication.
 * Protected by requireInternalToken.
 */

import { and, eq, inArray } from "drizzle-orm";
import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { db } from "../db";
import { assets, projects, renders } from "../db/schema";
import { sendError } from "../lib/errors";
import { recordUserEvent } from "../lib/userEvents";
import { requireInternalToken } from "../middleware/requireInternalToken";
import { validateBody } from "../middleware/validate";

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
    type: z.enum(["reference_video", "song", "clip", "render", "subtitle", "lut", "sfx"]),
    filename: z.string().min(1).max(255),
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
          }
        : null,
    };
  });

  // Create a new asset row for worker-generated outputs (e.g. renders, LUTs)
  app.post(
    "/api/internal/assets",
    { preHandler: validateBody(createAssetSchema) },
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
    { preHandler: validateBody(probeUpdateSchema) },
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

  // Mark a worker-generated asset as complete and set its public URL
  app.patch(
    "/api/internal/assets/:assetId/complete",
    { preHandler: validateBody(assetCompleteSchema) },
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
}
