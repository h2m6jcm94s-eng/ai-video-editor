import { FastifyInstance } from "fastify";
import { eq } from "drizzle-orm";
import { db } from "../db";
import { assets, projects } from "../db/schema";
import type { AssetType } from "@ai-video-editor/shared-types";
import { createPresignedUploadUrl, createPresignedDownloadUrl } from "../services/storage";
import { validateBody, presignedUploadSchema } from "../middleware/validate";

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
      return reply.status(404).send({ error: "Project not found", code: "NOT_FOUND" });
    }
    if (project.userId !== userId) {
      return reply.status(403).send({ error: "Forbidden", code: "FORBIDDEN" });
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

  // Complete upload and probe video metadata
  app.post("/:assetId/complete", async (request, reply) => {
    const { assetId } = request.params as { assetId: string };
    const body = request.body as { sizeBytes: number; etag: string; metadata?: any };

    if (body.sizeBytes < 0 || body.sizeBytes > 5 * 1024 * 1024 * 1024) {
      return reply.status(422).send({ error: "sizeBytes must be between 0 and 5GB", code: "VALIDATION_ERROR" });
    }

    const assetRow = await db.query.assets.findFirst({
      where: eq(assets.id, assetId),
    });
    if (!assetRow) {
      return reply.status(404).send({ error: "Asset not found", code: "NOT_FOUND" });
    }

    // Ownership check via project
    const userId = request.userId;
    const project = await db.query.projects.findFirst({
      where: eq(projects.id, assetRow.projectId),
    });
    if (!project || project.userId !== userId) {
      return reply.status(403).send({ error: "Forbidden", code: "FORBIDDEN" });
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
      return reply.status(404).send({ error: "Asset not found", code: "NOT_FOUND" });
    }

    return { asset };
  });

  // Get asset
  app.get("/:assetId", async (request, reply) => {
    const { assetId } = request.params as { assetId: string };
    const asset = await db.query.assets.findFirst({
      where: eq(assets.id, assetId),
    });

    if (!asset) {
      return reply.status(404).send({ error: "Asset not found", code: "NOT_FOUND" });
    }

    // Ownership check
    const userId = request.userId;
    const project = await db.query.projects.findFirst({
      where: eq(projects.id, asset.projectId),
    });
    if (!project || project.userId !== userId) {
      return reply.status(403).send({ error: "Forbidden", code: "FORBIDDEN" });
    }

    return { asset };
  });

  // Probe asset metadata (async ffprobe)
  app.post("/:assetId/probe", async (request, reply) => {
    const { assetId } = request.params as { assetId: string };
    const asset = await db.query.assets.findFirst({
      where: eq(assets.id, assetId),
    });

    if (!asset) {
      return reply.status(404).send({ error: "Asset not found", code: "NOT_FOUND" });
    }

    // Ownership check
    const userId = request.userId;
    const project = await db.query.projects.findFirst({
      where: eq(projects.id, asset.projectId),
    });
    if (!project || project.userId !== userId) {
      return reply.status(403).send({ error: "Forbidden", code: "FORBIDDEN" });
    }

    const body = request.body as { durationSec?: number; width?: number; height?: number; fps?: number };

    // Basic range validation
    if (body.durationSec !== undefined && (body.durationSec < 0 || body.durationSec > 86400)) {
      return reply.status(422).send({ error: "Invalid durationSec", code: "VALIDATION_ERROR" });
    }
    if (body.width !== undefined && (body.width < 1 || body.width > 7680)) {
      return reply.status(422).send({ error: "Invalid width", code: "VALIDATION_ERROR" });
    }
    if (body.height !== undefined && (body.height < 1 || body.height > 7680)) {
      return reply.status(422).send({ error: "Invalid height", code: "VALIDATION_ERROR" });
    }
    if (body.fps !== undefined && (body.fps < 1 || body.fps > 120)) {
      return reply.status(422).send({ error: "Invalid fps", code: "VALIDATION_ERROR" });
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
