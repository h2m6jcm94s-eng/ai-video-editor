// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
/**
 * Admin dashboard API routes.
 *
 * All routes require admin role (requireAdmin middleware).
 */

import { and, count, desc, eq, gte, lt, sql } from "drizzle-orm";
import { FastifyInstance } from "fastify";
import { db } from "../db";
import { adminAudit, projects, renders, userEvents, users } from "../db/schema";
import { sendError } from "../lib/errors";
import { requireAdmin } from "../middleware/requireAdmin";

export async function adminRoutes(app: FastifyInstance) {
  app.addHook("preHandler", requireAdmin);

  // Overview KPIs
  app.get("/overview", async () => {
    const now = new Date();
    const dayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);
    const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

    const [totalUsers] = await db.select({ count: count() }).from(users);
    const [activeUsers] = await db
      .select({ count: count() })
      .from(userEvents)
      .where(gte(userEvents.createdAt, dayAgo));
    const [totalErrors] = await db.select({ count: count() }).from(userEvents);
    const [recentErrors] = await db
      .select({ count: count() })
      .from(userEvents)
      .where(gte(userEvents.createdAt, dayAgo));
    const [totalRenders] = await db.select({ count: count() }).from(renders);
    const [queuedRenders] = await db
      .select({ count: count() })
      .from(renders)
      .where(eq(renders.status, "queued"));
    const [runningRenders] = await db
      .select({ count: count() })
      .from(renders)
      .where(eq(renders.status, "running"));

    return {
      users: { total: totalUsers.count, active24h: activeUsers.count },
      errors: { total: totalErrors.count, last24h: recentErrors.count },
      renders: { total: totalRenders.count, queued: queuedRenders.count, running: runningRenders.count },
    };
  });

  // User list (paginated)
  app.get("/users", async (request) => {
    const query = request.query as Record<string, string>;
    const limit = Math.min(parseInt(query.limit || "20", 10), 100);
    const cursor = query.cursor;

    const conditions = cursor ? [lt(users.createdAt, new Date(cursor))] : [];

    const userList = await db.query.users.findMany({
      where: and(...conditions),
      orderBy: [desc(users.createdAt)],
      limit: limit + 1,
    });

    const hasMore = userList.length > limit;
    const items = hasMore ? userList.slice(0, limit) : userList;
    const nextCursor =
      hasMore && items.length > 0 ? items[items.length - 1].createdAt?.toISOString() : undefined;

    return { items, nextCursor, hasMore };
  });

  // User detail
  app.get("/users/:userId", async (request, reply) => {
    const { userId } = request.params as { userId: string };

    const user = await db.query.users.findFirst({
      where: eq(users.id, userId),
    });
    if (!user) {
      return sendError(reply, 404, "User not found", "NOT_FOUND");
    }

    const [errorCount] = await db
      .select({ count: count() })
      .from(userEvents)
      .where(eq(userEvents.userId, userId));
    const [projectCount] = await db
      .select({ count: count() })
      .from(projects)
      .where(eq(projects.userId, userId));
    const [renderCount] = await db
      .select({ count: count() })
      .from(renders)
      .where(eq(renders.projectId, sql`(SELECT id FROM projects WHERE user_id = ${userId})`));

    return {
      user,
      stats: {
        errors: errorCount.count,
        projects: projectCount.count,
        renders: renderCount.count,
      },
    };
  });

  // Error log (paginated)
  app.get("/errors", async (request) => {
    const query = request.query as Record<string, string>;
    const limit = Math.min(parseInt(query.limit || "50", 10), 200);
    const cursor = query.cursor;

    const conditions = cursor ? [lt(userEvents.createdAt, new Date(cursor))] : [];
    const events = await db.query.userEvents.findMany({
      where: and(...conditions),
      orderBy: [desc(userEvents.createdAt)],
      limit: limit + 1,
    });

    const hasMore = events.length > limit;
    const items = hasMore ? events.slice(0, limit) : events;
    const nextCursor =
      hasMore && items.length > 0 ? items[items.length - 1].createdAt?.toISOString() : undefined;

    return { items, nextCursor, hasMore };
  });

  // Render queue health
  app.get("/renders", async () => {
    const renderList = await db.query.renders.findMany({
      orderBy: [desc(renders.createdAt)],
      limit: 100,
      with: { project: true },
    });

    const statusCounts = await db
      .select({ status: renders.status, count: count() })
      .from(renders)
      .groupBy(renders.status);

    return { items: renderList, statusCounts };
  });

  // Audit log (paginated)
  app.get("/audit", async (request) => {
    const query = request.query as Record<string, string>;
    const limit = Math.min(parseInt(query.limit || "50", 10), 200);
    const cursor = query.cursor;

    const conditions = cursor ? [lt(adminAudit.createdAt, new Date(cursor))] : [];
    const logs = await db.query.adminAudit.findMany({
      where: and(...conditions),
      orderBy: [desc(adminAudit.createdAt)],
      limit: limit + 1,
    });

    const hasMore = logs.length > limit;
    const items = hasMore ? logs.slice(0, limit) : logs;
    const nextCursor =
      hasMore && items.length > 0 ? items[items.length - 1].createdAt?.toISOString() : undefined;

    return { items, nextCursor, hasMore };
  });
}
