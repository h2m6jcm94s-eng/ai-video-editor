import { FastifyInstance } from "fastify";
import { eq, desc, and, inArray } from "drizzle-orm";
import { db } from "../db";
import { renders, projects } from "../db/schema";
import { enqueueJob } from "../services/queue";
import { startRenderWorkflow } from "../services/temporal";
import { validateBody, createRenderSchema } from "../middleware/validate";

export async function renderRoutes(app: FastifyInstance) {
  // Start render
  app.post("/", { preHandler: validateBody(createRenderSchema) }, async (request, reply) => {
    const body = request.validatedBody as { projectId: string; options?: Record<string, unknown> };
    const userId = request.userId;

    // Validate project exists and user owns it
    const project = await db.query.projects.findFirst({
      where: eq(projects.id, body.projectId),
    });
    if (!project) {
      return reply.status(404).send({ error: "Project not found", code: "NOT_FOUND" });
    }
    if (project.userId !== userId) {
      return reply.status(403).send({ error: "Forbidden", code: "FORBIDDEN" });
    }

    // Validate project has required assets
    if (!project.referenceAssetId || !project.songAssetId) {
      return reply.status(422).send({
        error: "Project missing reference asset or song",
        code: "MISSING_ASSETS",
      });
    }

    // Idempotency: prevent duplicate in-progress renders
    const existing = await db.query.renders.findFirst({
      where: and(
        eq(renders.projectId, body.projectId),
        inArray(renders.status, ["queued", "running"])
      ),
    });
    if (existing) {
      return reply.status(409).send({ error: "Render already in progress", code: "CONFLICT", jobId: existing.id });
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

    // Start Temporal workflow
    let workflowId: string;
    try {
      workflowId = await startRenderWorkflow(
        project.id,
        project.referenceAssetId,
        project.songAssetId,
        (project.clipAssetIds as string[]) || [],
        project.styleTier,
        project.mode,
        userId,
        job.id
      );
    } catch (e) {
      // Mark render as failed and return 500 without crashing
      await db.update(renders).set({ status: "failed", errorMessage: "Temporal workflow failed" }).where(eq(renders.id, job.id));
      return reply.status(500).send({ error: "Render engine unavailable", code: "TEMPORAL_ERROR" });
    }

    await db
      .update(renders)
      .set({ workflowId })
      .where(eq(renders.id, job.id));

    // Enqueue to Redis/Temporal
    await enqueueJob({
      jobId: job.id,
      projectId: body.projectId,
      type: "video_render",
      payload: body.options || {},
      priority: 1,
      createdAt: new Date().toISOString(),
    });

    // Update project status
    await db
      .update(projects)
      .set({ status: "rendering", updatedAt: new Date() })
      .where(eq(projects.id, body.projectId));

    return { job: { ...job, workflowId } };
  });

  // Get render job
  app.get("/:jobId", async (request, reply) => {
    const { jobId } = request.params as { jobId: string };
    const userId = request.userId;

    const job = await db.query.renders.findFirst({
      where: eq(renders.id, jobId),
    });

    if (!job) {
      return reply.status(404).send({ error: "Job not found", code: "NOT_FOUND" });
    }

    const project = await db.query.projects.findFirst({
      where: eq(projects.id, job.projectId),
    });
    if (!project || project.userId !== userId) {
      return reply.status(403).send({ error: "Forbidden", code: "FORBIDDEN" });
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
      return reply.status(403).send({ error: "Forbidden", code: "FORBIDDEN" });
    }

    const projectRenders = await db.query.renders.findMany({
      where: eq(renders.projectId, projectId),
      orderBy: [desc(renders.createdAt)],
    });
    return { jobs: projectRenders };
  });
}
