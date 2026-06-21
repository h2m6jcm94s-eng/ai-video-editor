// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
/**
 * Notification routes for per-user error events.
 *
 * - GET /api/notifications — list paginated unacknowledged events
 * - POST /api/notifications/:id/ack — acknowledge single event
 * - POST /api/notifications/ack-all — acknowledge all events
 * - GET /api/notifications/events — SSE stream for live updates
 */

import { and, count, desc, eq, lt } from "drizzle-orm";
import { FastifyInstance } from "fastify";
import Redis from "ioredis";
import { z } from "zod";
import { db } from "../db";
import { userEvents } from "../db/schema";
import { sendError } from "../lib/errors";
import { requireInternalToken } from "../middleware/requireInternalToken";
import { validateBody } from "../middleware/validate";
import { publishNotification } from "../services/queue";

const redis = new Redis(process.env.REDIS_URL || "redis://localhost:6379");

export async function notificationRoutes(app: FastifyInstance) {
  // SSE endpoint for live notification updates
  app.get(
    "/events",
    { config: { rateLimit: { max: 30, timeWindow: "1 minute" } } },
    async (request, reply) => {
      const userId = request.userId;
      if (!userId) {
        return sendError(reply, 401, "Sign in required", "UNAUTHORIZED");
      }

      reply.raw.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      });

      reply.raw.write(`data: ${JSON.stringify({ type: "connected" })}

`);

      const channel = `user:${userId}:events`;
      const subscriber = new Redis(process.env.REDIS_URL || "redis://localhost:6379");
      await subscriber.subscribe(channel);

      const messageHandler = (ch: string, message: string) => {
        if (ch === channel) {
          reply.raw.write(`data: ${message}

`);
        }
      };
      subscriber.on("message", messageHandler);

      const heartbeat = setInterval(() => {
        reply.raw.write(`:heartbeat

`);
      }, 15000);

      const cleanup = async () => {
        clearInterval(heartbeat);
        try {
          await subscriber.unsubscribe(channel);
        } catch {
          // ignore
        }
        try {
          await subscriber.quit();
        } catch {
          // ignore
        }
      };

      request.raw.on("close", cleanup);
      request.raw.on("aborted", cleanup);
      request.raw.on("error", cleanup);
      reply.raw.on("error", cleanup);
    },
  );

  // List notifications (paginated, cursor-based)
  app.get("/", { config: { rateLimit: { max: 60, timeWindow: "1 minute" } } }, async (request, reply) => {
    const userId = request.userId;
    if (!userId) {
      return sendError(reply, 401, "Sign in required", "UNAUTHORIZED");
    }

    const query = request.query as Record<string, string>;
    const limit = Math.min(parseInt(query.limit || "20", 10), 100);
    const cursor = query.cursor;

    const conditions = [eq(userEvents.userId, userId), eq(userEvents.acknowledged, false)];
    if (cursor) {
      const cursorDate = new Date(cursor);
      if (!isNaN(cursorDate.getTime())) {
        // Fetch events strictly older than the cursor timestamp.
        conditions.push(lt(userEvents.createdAt, cursorDate));
      }
    }

    const events = await db.query.userEvents.findMany({
      where: and(...conditions),
      orderBy: [desc(userEvents.createdAt)],
      limit: limit + 1,
    });

    const hasMore = events.length > limit;
    const items = hasMore ? events.slice(0, limit) : events;
    const nextCursor =
      hasMore && items.length > 0 ? items[items.length - 1].createdAt?.toISOString() : undefined;

    return {
      items,
      nextCursor,
      hasMore,
    };
  });

  // Acknowledge single event
  app.post(
    "/:id/ack",
    { config: { rateLimit: { max: 30, timeWindow: "1 minute" } } },
    async (request, reply) => {
      const userId = request.userId;
      if (!userId) {
        return sendError(reply, 401, "Sign in required", "UNAUTHORIZED");
      }

      const { id } = request.params as { id: string };

      const [updated] = await db
        .update(userEvents)
        .set({ acknowledged: true, updatedAt: new Date() })
        .where(and(eq(userEvents.id, id), eq(userEvents.userId, userId)))
        .returning();

      if (!updated) {
        return sendError(reply, 404, "Notification not found", "NOT_FOUND");
      }

      return { ok: true };
    },
  );

  // Acknowledge all events
  app.post(
    "/ack-all",
    { config: { rateLimit: { max: 10, timeWindow: "1 minute" } } },
    async (request, reply) => {
      const userId = request.userId;
      if (!userId) {
        return sendError(reply, 401, "Sign in required", "UNAUTHORIZED");
      }

      await db
        .update(userEvents)
        .set({ acknowledged: true, updatedAt: new Date() })
        .where(and(eq(userEvents.userId, userId), eq(userEvents.acknowledged, false)));

      return { ok: true };
    },
  );

  const internalEventSchema = z.object({
    userId: z.string().uuid(),
    code: z.string().min(1).max(50),
    message: z.string().min(1).max(2000),
    details: z.record(z.unknown()).optional(),
    route: z.string().max(255).optional(),
  });

  // Internal endpoint for workers to report user events
  app.post(
    "/internal",
    {
      preHandler: [requireInternalToken, validateBody(internalEventSchema)],
      config: { rateLimit: { max: 60, timeWindow: "1 minute" } },
    },
    async (request, reply) => {
      const body = request.validatedBody as z.infer<typeof internalEventSchema>;

      await db.insert(userEvents).values({
        userId: body.userId,
        code: body.code,
        message: body.message,
        // details is a jsonb column; pass the object directly to avoid double-stringifying.
        details: body.details ?? null,
        route: body.route ?? null,
      });

      // Publish to SSE channel so bell updates live
      await publishNotification(body.userId, {
        id: "internal",
        code: body.code,
        message: body.message,
        occurrenceCount: 1,
        createdAt: new Date().toISOString(),
      });

      return { ok: true };
    },
  );
}
