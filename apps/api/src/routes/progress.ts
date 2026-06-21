// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { eq } from "drizzle-orm";
import { FastifyInstance } from "fastify";
import Redis from "ioredis";
import { db } from "../db";
import { generationJobs, renders } from "../db/schema";
import { sendError } from "../lib/errors";
import { getBufferedEvents } from "../services/queue";

export async function progressRoutes(app: FastifyInstance) {
  // SSE endpoint for job progress
  app.get("/:jobId/events", async (request, reply) => {
    const { jobId } = request.params as { jobId: string };
    const userId = request.userId;

    // Auth check: verify user owns this render or generation job
    const renderJob = await db.query.renders.findFirst({
      where: eq(renders.id, jobId),
      with: { project: true },
    });
    const generationJob = renderJob
      ? null
      : await db.query.generationJobs?.findFirst({
          where: eq(generationJobs.id, jobId),
          with: { project: true },
        });
    const job = renderJob || generationJob;

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

    let subscriber: Redis | undefined;
    let heartbeat: NodeJS.Timeout | undefined;
    let cleaned = false;

    const cleanup = async () => {
      if (cleaned) return;
      cleaned = true;
      if (heartbeat) {
        clearInterval(heartbeat);
        heartbeat = undefined;
      }
      try {
        subscriber?.off("message", messageHandler);
        await subscriber?.unsubscribe(`job:${jobId}`);
      } catch {
        // ignore
      }
      try {
        await subscriber?.quit();
      } catch {
        // ignore
      }
      subscriber = undefined;
    };

    const messageHandler = (ch: string, message: string) => {
      if (ch === `job:${jobId}`) {
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

    try {
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

      // Subscribe to Redis channel (one subscriber per connection)
      subscriber = new Redis(process.env.REDIS_URL || "redis://localhost:6379");
      subscriber.on("error", (err) => {
        request.log.error({ err, jobId }, "Redis subscriber error");
        cleanup().catch(() => {});
      });
      await subscriber.subscribe(`job:${jobId}`);
      subscriber.on("message", messageHandler);

      // Keep connection alive
      heartbeat = setInterval(() => {
        reply.raw.write(`:heartbeat\n\n`);
      }, 15000);

      request.raw.on("close", () => cleanup().catch(() => {}));
      request.raw.on("aborted", () => cleanup().catch(() => {}));
      request.raw.on("error", () => cleanup().catch(() => {}));
      reply.raw.on("error", () => cleanup().catch(() => {}));
    } catch (err) {
      request.log.error({ err, jobId }, "SSE progress handler error");
      await cleanup();
      if (!reply.raw.writableEnded) {
        reply.raw.end();
      }
    }
  });
}
