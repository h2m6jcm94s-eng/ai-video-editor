// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { FastifyInstance } from "fastify";
import { eq } from "drizzle-orm";
import { HeadObjectCommand } from "@aws-sdk/client-s3";
import { z } from "zod";
import { db } from "../db";
import { assets, projects } from "../db/schema";
import type { AssetType } from "@ai-video-editor/shared-types";
import { createPresignedUploadUrl, createPresignedDownloadUrl, s3, BUCKET } from "../services/storage";
import { validateBody, presignedUploadSchema } from "../middleware/validate";
import { sendError } from "../lib/errors";

export async function uploadRoutes(app: FastifyInstance) {
  // Get presigned upload URL for multipart upload
  app.post("/presigned", { preHandler: validateBody(presignedUploadSchema) }, async (request, reply) => {
    const body = request.validatedBody as {
      projectId: string;
      filename: string;
      mimeType: string;
      type: AssetType;
      partNumber?: number;
      uploadId?: string;
    };

    // Ownership check
    const userId = request.userId;
    const project = await db.query.projects.findFirst({
      where: eq(projects.id, body.projectId),
    });
    if (!project) {
      return sendError(reply, 404, "Project not found", "NOT_FOUND");
    }
    if (project.userId !== userId) {
      return sendError(reply, 403, "Forbidden", "FORBIDDEN");
    }

    const assetId = crypto.randomUUID();
    const key = `projects/${body.projectId}/${body.type}/${assetId}-${body.filename}`;

    const { url, fields } = await createPresignedUploadUrl(key, body.mimeType);

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

    return { assetId, url, fields, key, asset };
  });

  const completeBodySchema = z.object({
    sizeBytes: z.number().int().min(0).max(5 * 1024 * 1024 * 1024),
    etag: z.string().min(1),
    metadata: z.record(z.unknown()).optional(),
  }).strict();

  // Complete upload and probe video metadata
  app.post("/:assetId/complete",
    { preHandler: validateBody(completeBodySchema) },
    async (request, reply) => {
      const { assetId } = request.params as { assetId: string };
      const body = request.validatedBody as z.infer<typeof completeBodySchema>;

      const assetRow = await db.query.assets.findFirst({
        where: eq(assets.id, assetId),
        with: { project: true },
      });
      if (!assetRow) {
        return sendError(reply, 404, "Asset not found", "NOT_FOUND");
      }

      // Ownership check via project
      const userId = request.userId;
      if (!assetRow.project || assetRow.project.userId !== userId) {
        return sendError(reply, 403, "Forbidden", "FORBIDDEN");
      }

      // Verify what's actually in R2 matches what client claims
      try {
        const head = await s3.send(new HeadObjectCommand({
          Bucket: BUCKET,
          Key: assetRow.storageKey,
        }));
        const actualEtag = head.ETag?.replace(/"/g, "");
        const claimedEtag = body.etag.replace(/"/g, "");
        if (actualEtag !== claimedEtag) {
          return sendError(reply, 409, "Upload ETag mismatch — content corrupted in transit", "ETAG_MISMATCH");
        }
        if (head.ContentLength !== body.sizeBytes) {
          return sendError(reply, 409, "Upload size mismatch", "ETAG_MISMATCH");
        }
      } catch (err) {
        return sendError(reply, 404, "Upload not found in storage", "UPLOAD_INCOMPLETE");
      }

      const storageUrl = await createPresignedDownloadUrl(assetRow.storageKey || "");

      const [asset] = await db
        .update(assets)
        .set({
          sizeBytes: body.sizeBytes,
          storageUrl,
          metadata: body.metadata || {},
        })
        .where(eq(assets.id, assetId))
        .returning();

      if (!asset) {
        return sendError(reply, 404, "Asset not found", "NOT_FOUND");
      }

      return { asset };
    }
  );

  // Get asset
  app.get("/:assetId", async (request, reply) => {
    const { assetId } = request.params as { assetId: string };
    const asset = await db.query.assets.findFirst({
      where: eq(assets.id, assetId),
      with: { project: true },
    });

    if (!asset) {
      return sendError(reply, 404, "Asset not found", "NOT_FOUND");
    }

    // Ownership check
    const userId = request.userId;
    if (!asset.project || asset.project.userId !== userId) {
      return sendError(reply, 403, "Forbidden", "FORBIDDEN");
    }

    return { asset };
  });

  // Probe asset metadata (async ffprobe)
  app.post("/:assetId/probe", async (request, reply) => {
    const { assetId } = request.params as { assetId: string };
    const asset = await db.query.assets.findFirst({
      where: eq(assets.id, assetId),
      with: { project: true },
    });

    if (!asset) {
      return sendError(reply, 404, "Asset not found", "NOT_FOUND");
    }

    // Ownership check
    const userId = request.userId;
    if (!asset.project || asset.project.userId !== userId) {
      return sendError(reply, 403, "Forbidden", "FORBIDDEN");
    }

    const body = request.body as { durationSec?: number; width?: number; height?: number; fps?: number };

    // Basic range validation
    if (body.durationSec !== undefined && (body.durationSec < 0 || body.durationSec > 86400)) {
      return sendError(reply, 422, "Invalid durationSec", "VALIDATION_ERROR");
    }
    if (body.width !== undefined && (body.width < 1 || body.width > 7680)) {
      return sendError(reply, 422, "Invalid width", "VALIDATION_ERROR");
    }
    if (body.height !== undefined && (body.height < 1 || body.height > 7680)) {
      return sendError(reply, 422, "Invalid height", "VALIDATION_ERROR");
    }
    if (body.fps !== undefined && (body.fps < 1 || body.fps > 120)) {
      return sendError(reply, 422, "Invalid fps", "VALIDATION_ERROR");
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
  });
}
