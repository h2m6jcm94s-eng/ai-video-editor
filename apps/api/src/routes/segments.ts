// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { eq } from "drizzle-orm";
import { FastifyInstance } from "fastify";
import { z } from "zod";
import { db } from "../db";
import { assets, projects } from "../db/schema";
import { sendError } from "../lib/errors";
import { validateBody } from "../middleware/validate";
import { getTemporalClient, startSegmentSubjectWorkflow } from "../services/temporal";

const createSegmentSchema = z
  .object({
    projectId: z.string().uuid(),
    assetId: z.string().uuid(),
    prompt: z.string().min(1).max(500),
    mode: z.enum(["image", "video"]).default("image"),
    frameIndex: z.number().int().min(0).default(0),
  })
  .strict();

export async function segmentRoutes(app: FastifyInstance) {
  // Start a segmentation job for an asset
  app.post("/", { preHandler: validateBody(createSegmentSchema) }, async (request, reply) => {
    const body = request.validatedBody as z.infer<typeof createSegmentSchema>;
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

    const asset = await db.query.assets.findFirst({
      where: eq(assets.id, body.assetId),
    });
    if (!asset || asset.projectId !== project.id) {
      return sendError(reply, 404, "Asset not found", "NOT_FOUND");
    }
    if (!asset.storageKey) {
      return sendError(reply, 422, "Asset upload not complete", "UPLOAD_INCOMPLETE");
    }

    try {
      const workflowId = await startSegmentSubjectWorkflow({
        assetId: asset.id,
        projectId: project.id,
        storageKey: asset.storageKey,
        prompt: body.prompt,
        mode: body.mode,
        frameIndex: body.frameIndex,
      });
      return reply.status(202).send({ workflowId, status: "queued" });
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      request.log.error({ err: e }, "Failed to start segment workflow");
      return sendError(reply, 500, "Segment engine unavailable", "TEMPORAL_ERROR", { message });
    }
  });

  // Query the result of a segmentation workflow
  app.get("/:workflowId", async (request, reply) => {
    const { workflowId } = request.params as { workflowId: string };
    const userId = request.userId;

    try {
      const client = await getTemporalClient();
      const handle = client.workflow.getHandle(workflowId);
      const result = await handle.query("get_result");
      return reply.send({ workflowId, result });
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      if (message.includes("not found") || message.includes("Workflow execution")) {
        return sendError(reply, 404, "Segment job not found", "NOT_FOUND");
      }
      return sendError(reply, 500, "Could not query segment job", "TEMPORAL_ERROR", { message });
    }
  });
}
