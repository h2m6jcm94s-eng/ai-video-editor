// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import Redis from "ioredis";
import { queueDepth } from "../lib/metrics";

const redis = new Redis(process.env.REDIS_URL || "redis://localhost:6379");

export interface JobMessage {
  jobId: string;
  projectId: string;
  type: string;
  payload: Record<string, unknown>;
  priority: number;
  createdAt: string;
}

export async function enqueueJob(message: JobMessage): Promise<void> {
  // Use a scored set for priority instead of a simple list
  const score = message.priority || 1;
  await redis.zadd("ave:jobs:queue", score, JSON.stringify(message));
  const depth = await redis.zcard("ave:jobs:queue");
  queueDepth.set(depth);
}

export async function dequeueJob(): Promise<JobMessage | null> {
  const data = await redis.zpopmin("ave:jobs:queue");
  const depth = await redis.zcard("ave:jobs:queue");
  queueDepth.set(depth);
  if (!data || data.length === 0) return null;
  try {
    return JSON.parse(data[1]);
  } catch (e) {
    // Log via stderr since this function has no request context
    // In production, this should be caught by a worker logger
    return null;
  }
}

const SSE_HISTORY_TTL_SEC = 300; // 5 minutes
const SSE_HISTORY_MAX = 50;

export async function publishProgress(
  jobId: string,
  stage: string,
  progress: number,
  message: string,
): Promise<void> {
  const eventId = await redis.incr(`ave:job:${jobId}:eventId`);
  const payload = JSON.stringify({ jobId, stage, progress, message, timestamp: new Date().toISOString() });

  // Publish to live subscribers
  await redis.publish(`job:${jobId}`, JSON.stringify({ id: eventId, data: payload }));

  // Buffer for reconnect resume
  const listKey = `ave:job:${jobId}:events`;
  await redis.lpush(listKey, JSON.stringify({ id: eventId, data: payload }));
  await redis.ltrim(listKey, 0, SSE_HISTORY_MAX - 1);
  await redis.expire(listKey, SSE_HISTORY_TTL_SEC);
}

export async function getBufferedEvents(
  jobId: string,
  afterId: number,
): Promise<{ id: number; data: string }[]> {
  const listKey = `ave:job:${jobId}:events`;
  const raw = await redis.lrange(listKey, 0, SSE_HISTORY_MAX - 1);
  const events: { id: number; data: string }[] = [];
  for (const item of raw.reverse()) {
    try {
      const parsed = JSON.parse(item);
      if (typeof parsed.id === "number" && parsed.id > afterId) {
        events.push(parsed);
      }
    } catch {
      // skip corrupt entries
    }
  }
  return events;
}

export async function getJobStatus(jobId: string): Promise<{
  stage: string;
  progress: number;
  message: string;
}> {
  const data = await redis.get(`ave:job:${jobId}:status`);
  if (!data) return { stage: "unknown", progress: 0, message: "" };
  try {
    return JSON.parse(data);
  } catch {
    return { stage: "unknown", progress: 0, message: "" };
  }
}

export async function setJobStatus(
  jobId: string,
  stage: string,
  progress: number,
  message: string,
): Promise<void> {
  await redis.setex(
    `ave:job:${jobId}:status`,
    86400, // 24 hours
    JSON.stringify({ stage, progress, message, updatedAt: new Date().toISOString() }),
  );
}

export async function publishNotification(
  userId: string,
  event: { id: string; code: string; message: string; occurrenceCount: number; createdAt: string },
): Promise<void> {
  await redis.publish(`user:${userId}:events`, JSON.stringify({ type: "notification", data: event }));
}

export async function probeRedis(): Promise<void> {
  await redis.ping();
}
