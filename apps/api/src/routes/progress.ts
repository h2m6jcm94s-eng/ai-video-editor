// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { FastifyInstance } from "fastify";
import Redis from "ioredis";
import { eq } from "drizzle-orm";
import { db } from "../db";
import { renders } from "../db/schema";
import { sendError } from "../lib/errors";

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

    // Send initial connection message
    reply.raw.write(`data: ${JSON.stringify({ type: "connected", jobId })}\n\n`);

    // Subscribe to Redis channel (reuse connection per channel)
    const channel = `job:${jobId}`;
    let subscriber = subscriberMap.get(channel);
    if (!subscriber) {
      subscriber = new Redis(process.env.REDIS_URL || "redis://localhost:6379");
      subscriber.on("error", (err) => {
        console.error("Redis subscriber error", { channel, err });
      });
      await subscriber.subscribe(channel);
      subscriberMap.set(channel, subscriber);
      subscriberRefCount.set(channel, 0);
    }
    subscriberRefCount.set(channel, (subscriberRefCount.get(channel) || 0) + 1);

    const messageHandler = (ch: string, message: string) => {
      if (ch === channel) {
        reply.raw.write(`data: ${message}\n\n`);
      }
    };
    subscriber.on("message", messageHandler);

    // Keep connection alive
    const heartbeat = setInterval(() => {
      reply.raw.write(`:heartbeat\n\n`);
    }, 15000);

    // Cleanup on close
    const cleanup = () => {
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
