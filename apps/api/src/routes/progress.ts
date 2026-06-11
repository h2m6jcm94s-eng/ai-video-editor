// Copyright (c) 2025 Devayan Dewri. All rights reserved.
import { eq } from "drizzle-orm";
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { FastifyInstance } from "fastify";
import Redis from "ioredis";
import { db } from "../db";
import { renders } from "../db/schema";
import { sendError } from "../lib/errors";
import { getBufferedEvents } from "../services/queue";

const redis = new Redis(process.env.REDIS_URL || "redis://localhost:6379");
const subscriberMap = new Map<string, Redis>();
const subscriberRefCount = new Map<string, number>();

export async function progressRoutes(app: FastifyInstance) {
  // SSE endpoint for job progress
  app.get("/:jobId/events", async (request, reply) => {
    const { jobId } = request.params as { jobId: string };
    const userId = request.userId;

    // Auth check: verify user owns this render job
    const job = await db.query.renders.findFirst({
      where: eq(renders.id, jobId),
      with: { project: true },
    });
    if (!job) {
      return sendError(reply, 404, "Job not found", "NOT_FOUND");
    }
    if (!job.project || job.project.userId !== userId) {
      return sendError(reply, 403, "Forbidden", "FORBIDDEN");
    }

    reply.raw.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    });

    // Replay missed events if client reconnects with Last-Event-ID header or query param
    const lastEventIdHeader = (request.headers["last-event-id"] as string) || "";
    const lastEventIdQuery = (request.query as Record<string, string>).lastEventId || "";
    const lastEventId = parseInt(lastEventIdHeader || lastEventIdQuery, 10);
    if (!isNaN(lastEventId) && lastEventId > 0) {
      const missed = await getBufferedEvents(jobId, lastEventId);
      for (const event of missed) {
        reply.raw.write(`id: ${event.id}\ndata: ${event.data}\n\n`);
      }
    }

    // Send initial connection message
    reply.raw.write(`data: ${JSON.stringify({ type: "connected", jobId })}\n\n`);

    // Subscribe to Redis channel (reuse connection per channel)
    const channel = `job:${jobId}`;
    let subscriber = subscriberMap.get(channel);
    if (!subscriber) {
      subscriber = new Redis(process.env.REDIS_URL || "redis://localhost:6379");
      subscriber.on("error", (err) => {
        request.log.error({ err, channel }, "Redis subscriber error");
      });
      await subscriber.subscribe(channel);
      subscriberMap.set(channel, subscriber);
      subscriberRefCount.set(channel, 0);
    }
    subscriberRefCount.set(channel, (subscriberRefCount.get(channel) || 0) + 1);

    const messageHandler = (ch: string, message: string) => {
      if (ch === channel) {
        try {
          const parsed = JSON.parse(message);
          if (parsed.id && parsed.data) {
            reply.raw.write(`id: ${parsed.id}\ndata: ${parsed.data}\n\n`);
          } else {
            reply.raw.write(`data: ${message}\n\n`);
          }
        } catch {
          reply.raw.write(`data: ${message}\n\n`);
        }
      }
    };
    subscriber.on("message", messageHandler);

    // Keep connection alive
    const heartbeat = setInterval(() => {
      reply.raw.write(`:heartbeat\n\n`);
    }, 15000);

    // Cleanup on close — guarded against double-fire from close + error
    let cleaned = false;
    const cleanup = () => {
      if (cleaned) return;
      cleaned = true;
      clearInterval(heartbeat);
      const refCount = (subscriberRefCount.get(channel) || 1) - 1;
      subscriberRefCount.set(channel, refCount);
      if (refCount <= 0) {
        subscriberMap.get(channel)?.unsubscribe(channel);
        subscriberMap.get(channel)?.quit();
        subscriberMap.delete(channel);
        subscriberRefCount.delete(channel);
      } else {
        subscriber?.off("message", messageHandler);
      }
    };

    request.raw.on("close", cleanup);
    request.raw.on("error", cleanup);
    reply.raw.on("error", cleanup);
  });
}
