// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { FastifyInstance } from "fastify";
import { eq, desc, and, inArray } from "drizzle-orm";
import { db } from "../db";
import { projects, assets, renders } from "../db/schema";
import type { ProjectStatus, StyleTier, EditMode } from "@ai-video-editor/shared-types";
import { sendCutlistApprovedSignal, startRenderWorkflow } from "../services/temporal";
import { deleteProjectAssets, downloadAsset } from "../services/storage";
import { validateBody, createProjectSchema, patchProjectSchema, updateCutlistSchema, promptEditSchema } from "../middleware/validate";
import { applyPromptEdit, transcribeAudio } from "../services/ai";
import fs from "fs";
import path from "path";
import os from "os";

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

  // Transcribe audio asset to subtitles
  app.post("/:id/transcribe", async (request, reply) => {
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

    const body = request.body as { assetId?: string };
    if (!body?.assetId) {
      return reply.status(400).send({ error: "assetId required", code: "VALIDATION_ERROR" });
    }

    const asset = await db.query.assets.findFirst({
      where: eq(assets.id, body.assetId),
    });
    if (!asset || asset.projectId !== id) {
      return reply.status(404).send({ error: "Asset not found", code: "NOT_FOUND" });
    }

    const tmpDir = os.tmpdir();
    const tmpFile = path.join(tmpDir, `transcribe-${asset.id}-${Date.now()}.mp3`);

    try {
      await downloadAsset(asset.storageKey, tmpFile);
      const audioBuffer = fs.readFileSync(tmpFile);
      const segments = await transcribeAudio(audioBuffer, asset.filename);

      const subtitles = segments.map((s, i) => ({
        id: `sub-${i}`,
        text: s.text,
        start_s: s.start,
        end_s: s.end,
      }));

      return { subtitles };
    } catch (err) {
      console.error("Transcription failed:", err);
      return reply.status(500).send({
        error: err instanceof Error ? err.message : "Transcription failed",
        code: "TRANSCRIBE_ERROR",
      });
    } finally {
      try {
        fs.unlinkSync(tmpFile);
      } catch {
        // ignore cleanup errors
      }
    }
  });

  // Prompt-to-edit (AI powered)
  app.post("/:id/prompt", { preHandler: validateBody(promptEditSchema) }, async (request, reply) => {
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

    const body = request.validatedBody as { prompt: string };
    if (!project.cutList) {
      return reply.status(400).send({ error: "No cutlist to edit", code: "NO_CUTLIST" });
    }

    // Gather assets for context
    const projectAssets = await db.query.assets.findMany({
      where: eq(assets.projectId, id),
    });

    try {
      const result = await applyPromptEdit({
        prompt: body.prompt,
        cutList: project.cutList,
        assets: (projectAssets || []).map((a) => ({
          id: a.id,
          type: a.type,
          filename: a.filename,
          durationSec: a.durationSec,
        })),
      });

      // Save the new cutlist
      const [updated] = await db
        .update(projects)
        .set({
          cutList: result.newCutList,
          updatedAt: new Date(),
        })
        .where(eq(projects.id, id))
        .returning();

      return {
        project: updated,
        diff: result.diff,
        explanation: result.explanation,
      };
    } catch (err) {
      console.error("Prompt edit failed:", err);
      return reply.status(500).send({
        error: err instanceof Error ? err.message : "AI edit failed",
        code: "AI_ERROR",
      });
    }
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
