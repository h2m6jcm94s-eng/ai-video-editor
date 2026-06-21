// Copyright (c) 2025 Devayan Dewri. All rights reserved.
import type { AssetType } from "@ai-video-editor/shared-types";
import { eq } from "drizzle-orm";
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { FastifyInstance } from "fastify";
import { z } from "zod";
import { db } from "../db";
import type { Asset } from "../db/schema";
import { assets, projects } from "../db/schema";
import { sendError } from "../lib/errors";
import { presignedUploadSchema, validateBody } from "../middleware/validate";
import {
  abortMultipartUpload,
  completeMultipartUpload,
  createMultipartUpload,
  createPresignedDownloadUrl,
  createPresignedUploadUrl,
  deleteAsset,
  headObject,
  presignUploadPart,
} from "../services/storage";
import { startAnalyzeStyleWorkflow, startProbeWorkflow } from "../services/temporal";

function normalizeClipAssetIds(value: unknown): string[] {
  if (Array.isArray(value)) return value as string[];
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      if (Array.isArray(parsed)) return parsed as string[];
    } catch {
      // fall through
    }
  }
  return [];
}

async function attachAssetToProject(asset: Asset) {
  if (asset.type === "reference_video") {
    await db
      .update(projects)
      .set({ referenceAssetId: asset.id, updatedAt: new Date() })
      .where(eq(projects.id, asset.projectId));
  } else if (asset.type === "song") {
    await db
      .update(projects)
      .set({ songAssetId: asset.id, updatedAt: new Date() })
      .where(eq(projects.id, asset.projectId));
  } else if (asset.type === "clip") {
    const project = await db.query.projects.findFirst({
      where: eq(projects.id, asset.projectId),
      columns: { clipAssetIds: true },
    });
    const current = normalizeClipAssetIds(project?.clipAssetIds);
    if (!current.includes(asset.id)) {
      await db
        .update(projects)
        .set({
          clipAssetIds: [...current, asset.id],
          updatedAt: new Date(),
        })
        .where(eq(projects.id, asset.projectId));
    }
  }
}

export async function uploadRoutes(app: FastifyInstance) {
  // Get presigned upload URL for simple (single-PUT) upload
  app.post("/presigned", { preHandler: validateBody(presignedUploadSchema) }, async (request, reply) => {
    const body = request.validatedBody as {
      projectId: string;
      filename: string;
      mimeType: string;
      type: AssetType;
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

    return { assetId, url, fields, asset };
  });

  const completeBodySchema = z
    .object({
      sizeBytes: z
        .number()
        .int()
        .min(0)
        .max(5 * 1024 * 1024 * 1024),
      etag: z.string().min(1),
      metadata: z.record(z.unknown()).optional(),
    })
    .strict();

  // Complete simple upload
  app.post("/:assetId/complete", { preHandler: validateBody(completeBodySchema) }, async (request, reply) => {
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
      const head = await headObject(assetRow.storageKey);
      const actualEtag = head.ETag?.replace(/"/g, "");
      const claimedEtag = body.etag.replace(/"/g, "");
      // Skip etag check for multipart uploads (multipart etag is a digest of part etags)
      if (!head.PartsCount && actualEtag !== claimedEtag) {
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

    // Trigger probe workflow for video/audio assets (fire-and-forget)
    if (["reference_video", "clip", "render", "song"].includes(asset.type)) {
      startProbeWorkflow(asset.id, asset.storageKey).catch((e) =>
        request.log.error({ err: e, assetId }, "probe trigger failed"),
      );
    }

    // Trigger richer style analysis for reference videos (fire-and-forget)
    if (asset.type === "reference_video") {
      startAnalyzeStyleWorkflow({
        assetId: asset.id,
        storageKey: asset.storageKey,
      }).catch((e) => request.log.error({ err: e, assetId }, "style analysis trigger failed"));
    }

    await attachAssetToProject(asset);

    return { asset };
  });

  // ── Multipart Upload Endpoints ───────────────────────────────────────────

  const multipartInitSchema = z
    .object({
      projectId: z.string().uuid(),
      filename: z.string().min(1).max(255),
      mimeType: z.string(),
      type: z.enum(["reference_video", "song", "clip", "render", "subtitle", "lut", "sfx"] as const),
    })
    .strict();

  app.post("/multipart/init", { preHandler: validateBody(multipartInitSchema) }, async (request, reply) => {
    const body = request.validatedBody as z.infer<typeof multipartInitSchema>;

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
    const uploadId = await createMultipartUpload(key, body.mimeType);

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
        metadata: { uploadId, isMultipart: true },
      })
      .returning();

    return { uploadId, key, assetId, asset };
  });

  const multipartSignSchema = z
    .object({
      uploadId: z.string().min(1),
      key: z.string().min(1),
      partNumber: z.number().int().min(1).max(10000),
    })
    .strict();

  app.post(
    "/multipart/sign-part",
    { preHandler: validateBody(multipartSignSchema) },
    async (request, reply) => {
      const body = request.validatedBody as z.infer<typeof multipartSignSchema>;

      // Ownership check: look up asset by storage key, verify via project FK
      const assetRow = await db.query.assets.findFirst({
        where: eq(assets.storageKey, body.key),
        with: { project: true },
      });
      if (!assetRow) {
        return sendError(reply, 404, "Asset not found", "NOT_FOUND");
      }
      const userId = request.userId;
      if (!assetRow.project || assetRow.project.userId !== userId) {
        return sendError(reply, 403, "Forbidden", "FORBIDDEN");
      }

      const url = await presignUploadPart(body.key, body.uploadId, body.partNumber);
      return { url };
    },
  );

  const multipartCompleteSchema = z
    .object({
      uploadId: z.string().min(1),
      key: z.string().min(1),
      parts: z
        .array(
          z.object({
            PartNumber: z.number().int().min(1),
            ETag: z.string().min(1),
          }),
        )
        .min(1),
      sizeBytes: z
        .number()
        .int()
        .min(0)
        .max(5 * 1024 * 1024 * 1024),
      metadata: z.record(z.unknown()).optional(),
    })
    .strict();

  app.post(
    "/multipart/complete",
    { preHandler: validateBody(multipartCompleteSchema) },
    async (request, reply) => {
      const body = request.validatedBody as z.infer<typeof multipartCompleteSchema>;

      const assetRow = await db.query.assets.findFirst({
        where: eq(assets.storageKey, body.key),
        with: { project: true },
      });
      if (!assetRow) {
        return sendError(reply, 404, "Asset not found", "NOT_FOUND");
      }

      const userId = request.userId;
      if (!assetRow.project || assetRow.project.userId !== userId) {
        return sendError(reply, 403, "Forbidden", "FORBIDDEN");
      }

      await completeMultipartUpload(body.key, body.uploadId, body.parts);

      // Verify the assembled object size matches what the client claimed.
      const head = await headObject(body.key);
      const actualSize = head.ContentLength ?? -1;
      if (actualSize !== body.sizeBytes) {
        await deleteAsset(body.key).catch((err) =>
          request.log.error({ err, key: body.key }, "Failed to delete mismatched multipart upload"),
        );
        return sendError(
          reply,
          422,
          `Assembled file size ${actualSize} does not match expected ${body.sizeBytes}`,
          "VALIDATION_ERROR",
        );
      }

      const storageUrl = await createPresignedDownloadUrl(body.key);

      const [asset] = await db
        .update(assets)
        .set({
          sizeBytes: body.sizeBytes,
          storageUrl,
          metadata: { ...(assetRow.metadata || {}), isMultipart: true },
        })
        .where(eq(assets.id, assetRow.id))
        .returning();

      if (!asset) {
        return sendError(reply, 404, "Asset not found", "NOT_FOUND");
      }

      // Trigger probe workflow for video/audio assets (fire-and-forget)
      if (["reference_video", "clip", "render", "song"].includes(asset.type)) {
        startProbeWorkflow(asset.id, asset.storageKey).catch((e) =>
          request.log.error({ err: e, assetId: asset.id }, "probe trigger failed"),
        );
      }

      // Trigger richer style analysis for reference videos (fire-and-forget)
      if (asset.type === "reference_video") {
        startAnalyzeStyleWorkflow({
          assetId: asset.id,
          storageKey: asset.storageKey,
        }).catch((e) => request.log.error({ err: e, assetId: asset.id }, "style analysis trigger failed"));
      }

      await attachAssetToProject(asset);

      return { asset };
    },
  );

  const multipartAbortSchema = z
    .object({
      uploadId: z.string().min(1),
      key: z.string().min(1),
    })
    .strict();

  app.delete(
    "/multipart/abort",
    { preHandler: validateBody(multipartAbortSchema) },
    async (request, reply) => {
      const body = request.validatedBody as z.infer<typeof multipartAbortSchema>;

      // Ownership check: aborting an upload modifies S3 state for this asset
      const assetRow = await db.query.assets.findFirst({
        where: eq(assets.storageKey, body.key),
        with: { project: true },
      });
      if (!assetRow) {
        return sendError(reply, 404, "Asset not found", "NOT_FOUND");
      }
      const userId = request.userId;
      if (!assetRow.project || assetRow.project.userId !== userId) {
        return sendError(reply, 403, "Forbidden", "FORBIDDEN");
      }

      await abortMultipartUpload(body.key, body.uploadId);
      return { ok: true };
    },
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
  const probeBodySchema = z
    .object({
      durationSec: z.number().min(0).max(86400).optional(),
      width: z.number().int().min(1).max(7680).optional(),
      height: z.number().int().min(1).max(7680).optional(),
      fps: z.number().min(1).max(120).optional(),
    })
    .strict();

  app.post("/:assetId/probe", { preHandler: validateBody(probeBodySchema) }, async (request, reply) => {
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

    const body = request.validatedBody as z.infer<typeof probeBodySchema>;

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
