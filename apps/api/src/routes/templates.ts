// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.

import { desc, eq, or } from "drizzle-orm";
import { FastifyInstance } from "fastify";
import { db } from "../db";
import { templates } from "../db/schema";
import { cacheDel, cacheGet, cacheSet } from "../lib/cache";
import { sendError } from "../lib/errors";
import { createTemplateSchema, validateBody } from "../middleware/validate";

export async function templateRoutes(app: FastifyInstance) {
  // List templates (user's own + public)
  app.get("/", async (request, _reply) => {
    const userId = request.userId;
    const cacheKey = `templates:list:${userId}`;
    const cached = await cacheGet<typeof userTemplates>(cacheKey);
    if (cached) {
      return { templates: cached };
    }
    const userTemplates = await db.query.templates.findMany({
      where: or(eq(templates.userId, userId), eq(templates.isPublic, true)),
      orderBy: [desc(templates.updatedAt)],
    });
    await cacheSet(cacheKey, userTemplates);
    return { templates: userTemplates };
  });

  // Create template from current cutlist
  app.post("/", { preHandler: validateBody(createTemplateSchema) }, async (request, _reply) => {
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

    await cacheDel(`templates:list:${userId}`);
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
      return sendError(reply, 404, "Not found", "NOT_FOUND");
    }
    if (template.userId !== userId && !template.isPublic) {
      return sendError(reply, 403, "Forbidden", "FORBIDDEN");
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
      return sendError(reply, 404, "Not found", "NOT_FOUND");
    }
    if (template.userId !== userId) {
      return sendError(reply, 403, "Forbidden", "FORBIDDEN");
    }

    const body = request.body as Partial<typeof templates.$inferInsert>;
    const [updated] = await db
      .update(templates)
      .set({ ...body, updatedAt: new Date() })
      .where(eq(templates.id, id))
      .returning();

    await cacheDel(`templates:list:${userId}`);
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
      return sendError(reply, 404, "Not found", "NOT_FOUND");
    }
    if (template.userId !== userId) {
      return sendError(reply, 403, "Forbidden", "FORBIDDEN");
    }

    await db.delete(templates).where(eq(templates.id, id));
    await cacheDel(`templates:list:${userId}`);
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
      return sendError(reply, 404, "Not found", "NOT_FOUND");
    }
    if (template.userId !== userId && !template.isPublic) {
      return sendError(reply, 403, "Forbidden", "FORBIDDEN");
    }

    await db
      .update(templates)
      .set({ usageCount: (template.usageCount || 0) + 1 })
      .where(eq(templates.id, id));

    return { cutList: template.cutList };
  });
}
