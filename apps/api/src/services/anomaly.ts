// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
/**
 * Lightweight anomaly detection for API usage patterns.
 *
 * Uses simple statistical methods (Z-score over a rolling window)
 * to flag unusual behaviour without ML infrastructure.
 */

import Redis from "ioredis";
import { logger } from "../lib/logger";
import { anomaliesDetectedTotal } from "../lib/metrics";

const redis = new Redis(process.env.REDIS_URL || "redis://localhost:6379");

const ANOMALY_WINDOW_MS = 5 * 60 * 1000; // 5 minutes
const Z_SCORE_THRESHOLD = 3.0;

export interface AnomalyEvent {
  userId: string;
  metric: string;
  value: number;
  expected: number;
  zScore: number;
  timestamp: string;
}

/**
 * Record a metric sample for a user. Returns an anomaly event if the
 * current value is statistically unusual compared to the user's history.
 */
export async function recordMetric(
  userId: string,
  metric: string,
  value: number,
): Promise<AnomalyEvent | null> {
  const key = `anomaly:${userId}:${metric}`;
  const now = Date.now();

  try {
    // Add current sample
    const member = `${now}-${Math.random().toString(36).slice(2, 8)}`;
    await redis.zadd(key, now, member);
    await redis.pexpire(key, ANOMALY_WINDOW_MS * 2);

    // Evict old samples
    const windowStart = now - ANOMALY_WINDOW_MS;
    await redis.zremrangebyscore(key, 0, windowStart);

    // Fetch remaining samples in window
    const samplesRaw = await redis.zrange(key, 0, -1, "WITHSCORES");
    const samples: number[] = [];
    for (let i = 0; i < samplesRaw.length; i += 2) {
      // The member format is "timestamp-random", but the score IS the timestamp.
      // To store actual values we'd need a hash or JSON. For latency/simplicity
      // we approximate: each request = value 1 for "request_count" metric,
      // otherwise we store the value in the member and parse it.
      const memberParts = samplesRaw[i].split("-");
      const storedValue = memberParts.length > 2 ? parseFloat(memberParts[2]) : 1;
      samples.push(Number.isFinite(storedValue) ? storedValue : 1);
    }

    if (samples.length < 5) {
      // Not enough data for statistical significance
      return null;
    }

    const mean = samples.reduce((a, b) => a + b, 0) / samples.length;
    const variance = samples.reduce((sum, v) => sum + (v - mean) ** 2, 0) / samples.length;
    const stdDev = Math.sqrt(variance);

    if (stdDev === 0) {
      return null; // No variance = no anomaly possible
    }

    const zScore = Math.abs((value - mean) / stdDev);
    if (zScore > Z_SCORE_THRESHOLD) {
      const event: AnomalyEvent = {
        userId,
        metric,
        value,
        expected: mean,
        zScore: Math.round(zScore * 100) / 100,
        timestamp: new Date().toISOString(),
      };
      await publishAnomaly(event);
      return event;
    }

    return null;
  } catch (e) {
    logger.error({ err: e, userId, metric }, "Anomaly detection failed");
    return null;
  }
}

/**
 * Record a metric with an explicit numeric value (not just a counter).
 * Stores the value inside the Redis member for later retrieval.
 */
export async function recordNumericMetric(
  userId: string,
  metric: string,
  value: number,
): Promise<AnomalyEvent | null> {
  const key = `anomaly:${userId}:${metric}`;
  const now = Date.now();

  try {
    const member = `${now}-${Math.random().toString(36).slice(2, 8)}-${value}`;
    await redis.zadd(key, now, member);
    await redis.pexpire(key, ANOMALY_WINDOW_MS * 2);

    const windowStart = now - ANOMALY_WINDOW_MS;
    await redis.zremrangebyscore(key, 0, windowStart);

    const samplesRaw = await redis.zrange(key, 0, -1, "WITHSCORES");
    const samples: number[] = [];
    for (let i = 0; i < samplesRaw.length; i += 2) {
      const parts = samplesRaw[i].split("-");
      const v = parts.length >= 3 ? parseFloat(parts[parts.length - 1]) : 1;
      samples.push(Number.isFinite(v) ? v : 1);
    }

    if (samples.length < 5) return null;

    const mean = samples.reduce((a, b) => a + b, 0) / samples.length;
    const variance = samples.reduce((sum, v) => sum + (v - mean) ** 2, 0) / samples.length;
    const stdDev = Math.sqrt(variance);

    if (stdDev === 0) return null;

    const zScore = Math.abs((value - mean) / stdDev);
    if (zScore > Z_SCORE_THRESHOLD) {
      const event: AnomalyEvent = {
        userId,
        metric,
        value,
        expected: mean,
        zScore: Math.round(zScore * 100) / 100,
        timestamp: new Date().toISOString(),
      };
      await publishAnomaly(event);
      return event;
    }

    return null;
  } catch (e) {
    logger.error({ err: e, userId, metric }, "Anomaly detection failed");
    return null;
  }
}

async function publishAnomaly(event: AnomalyEvent): Promise<void> {
  await redis.publish("ave:anomalies", JSON.stringify(event));
  await redis.lpush("ave:anomalies:recent", JSON.stringify(event));
  await redis.ltrim("ave:anomalies:recent", 0, 99);
  anomaliesDetectedTotal.inc({ metric: event.metric });
  logger.warn({ event }, "Anomaly detected");
}

/**
 * List recent anomalies for admin review.
 */
export async function listRecentAnomalies(
  _opts: { limit?: number; since?: string } = {},
): Promise<AnomalyEvent[]> {
  // In a production system this would read from a persistent store.
  // For now we keep a capped list in Redis.
  const raw = await redis.lrange("ave:anomalies:recent", 0, 99);
  const events: AnomalyEvent[] = [];
  for (const item of raw) {
    try {
      events.push(JSON.parse(item));
    } catch {
      // skip corrupt
    }
  }
  return events;
}
