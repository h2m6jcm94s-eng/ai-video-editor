// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { FastifyInstance } from "fastify";
import { eq, desc, or } from "drizzle-orm";
import { db } from "../db";
import { templates } from "../db/schema";
import { validateBody, createTemplateSchema } from "../middleware/validate";

export async function templateRoutes(app: FastifyInstance) {
  // List templates (user's own + public)
  app.get("/", async (request, reply) => {
    const userId = request.userId;
    const userTemplates = await db.query.templates.findMany({
      where: or(eq(templates.userId, userId), eq(templates.isPublic, true)),
      orderBy: [desc(templates.updatedAt)],
    });
    return { templates: userTemplates };
  });

  // Create template from current cutlist
  app.post("/", { preHandler: validateBody(createTemplateSchema) }, async (request, reply) => {
    const userId = request.userId;
    const body = request.validatedBody as {
      name: string;
      description?: string;
      cutList: unknown;
      tags?: string[];
      isPublic?: boolean;
    };

    const [template] = await db
      .insert(templates)
      .values({
        name: body.name,
        description: body.description || null,
        cutList: body.cutList,
        tags: body.tags || [],
        isPublic: body.isPublic || false,
        userId,
      })
      .returning();

    return { template };
  });

  // Get template
  app.get("/:id", async (request, reply) => {
    const { id } = request.params as { id: string };
    const userId = request.userId;
    const template = await db.query.templates.findFirst({
      where: eq(templates.id, id),
    });
    if (!template) {
      return reply.status(404).send({ error: "Not found", code: "NOT_FOUND" });
    }
    if (template.userId !== userId && !template.isPublic) {
      return reply.status(403).send({ error: "Forbidden", code: "FORBIDDEN" });
    }
    return { template };
  });

  // Update template
  app.patch("/:id", async (request, reply) => {
    const { id } = request.params as { id: string };
    const userId = request.userId;
    const template = await db.query.templates.findFirst({
      where: eq(templates.id, id),
    });
    if (!template) {
      return reply.status(404).send({ error: "Not found", code: "NOT_FOUND" });
    }
    if (template.userId !== userId) {
      return reply.status(403).send({ error: "Forbidden", code: "FORBIDDEN" });
    }

    const body = request.body as Partial<typeof templates.$inferInsert>;
    const [updated] = await db
      .update(templates)
      .set({ ...body, updatedAt: new Date() })
      .where(eq(templates.id, id))
      .returning();

    return { template: updated };
  });

  // Delete template
  app.delete("/:id", async (request, reply) => {
    const { id } = request.params as { id: string };
    const userId = request.userId;
    const template = await db.query.templates.findFirst({
      where: eq(templates.id, id),
    });
    if (!template) {
      return reply.status(404).send({ error: "Not found", code: "NOT_FOUND" });
    }
    if (template.userId !== userId) {
      return reply.status(403).send({ error: "Forbidden", code: "FORBIDDEN" });
    }

    await db.delete(templates).where(eq(templates.id, id));
    return { success: true };
  });

  // Apply template to project (increment usage)
  app.post("/:id/apply", async (request, reply) => {
    const { id } = request.params as { id: string };
    const userId = request.userId;
    const template = await db.query.templates.findFirst({
      where: eq(templates.id, id),
    });
    if (!template) {
      return reply.status(404).send({ error: "Not found", code: "NOT_FOUND" });
    }
    if (template.userId !== userId && !template.isPublic) {
      return reply.status(403).send({ error: "Forbidden", code: "FORBIDDEN" });
    }

    await db
      .update(templates)
      .set({ usageCount: (template.usageCount || 0) + 1 })
      .where(eq(templates.id, id));

    return { cutList: template.cutList };
  });
}
