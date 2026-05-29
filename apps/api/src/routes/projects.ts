// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { FastifyInstance } from "fastify";
import { eq, desc, and, inArray } from "drizzle-orm";
import { db } from "../db";
import { projects, assets, renders } from "../db/schema";
import type { ProjectStatus, StyleTier, EditMode } from "@ai-video-editor/shared-types";
import { sendCutlistApprovedSignal, startRenderWorkflow } from "../services/temporal";
import { deleteProjectAssets } from "../services/storage";
import { validateBody, createProjectSchema, patchProjectSchema, updateCutlistSchema } from "../middleware/validate";

export async function projectRoutes(app: FastifyInstance) {
  // List projects for user
  app.get("/", async (request, reply) => {
    const userId = request.userId;
    const userProjects = await db.query.projects.findMany({
      where: eq(projects.userId, userId),
      orderBy: [desc(projects.updatedAt)],
      with: {
        assets: true,
      },
    });
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

    return { project };
  });

  // Get project
  app.get("/:id", async (request, reply) => {
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
    const fullProject = await db.query.projects.findFirst({
      where: eq(projects.id, id),
      with: { assets: true },
    });
    return { project: fullProject };
  });

  // Update project
  app.patch("/:id", { preHandler: validateBody(patchProjectSchema) }, async (request, reply) => {
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

    const body = request.validatedBody as Partial<typeof projects.$inferInsert>;
    const [updated] = await db
      .update(projects)
      .set({ ...body, updatedAt: new Date() })
      .where(eq(projects.id, id))
      .returning();

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
      return reply.status(404).send({ error: "Not found", code: "NOT_FOUND" });
    }
    if (project.userId !== userId) {
      return reply.status(403).send({ error: "Forbidden", code: "FORBIDDEN" });
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
      console.error("Failed to delete assets for project", { projectId: id, err });
    });

    await db.delete(projects).where(eq(projects.id, id));
    return { success: true };
  });
}
