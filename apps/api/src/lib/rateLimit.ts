// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
/**
 * Redis-backed sliding-window rate limiter.
 *
 * More accurate than fixed-window counters because it tracks every
 * request timestamp and evicts entries outside the window.
 */

import { logger } from "./logger";
import { slidingWindowRejectsTotal } from "./metrics";
import { redis } from "./redis";

export interface RateLimitResult {
  allowed: boolean;
  remaining: number;
  resetMs: number;
  limit: number;
  windowMs: number;
}

interface SlidingWindowOpts {
  /** Max requests per window */
  limit: number;
  /** Window size in milliseconds */
  windowMs: number;
  /** Unique key prefix (e.g. "rl:prompt:user-123") */
  key: string;
  /** Cost of this request (default 1) */
  cost?: number;
  /**
   * When true, Redis failures reject the request instead of allowing it.
   * Use for expensive or mutating endpoints (AI prompts, uploads, etc.).
   */
  failClosed?: boolean;
}

/**
 * Check and consume a request against a sliding window.
 *
 * Algorithm:
 * 1. ZREMRANGEBYSCORE key 0 (now - windowMs)  → evict old entries
 * 2. ZCARD key                                 → count current entries
 * 3. If count + cost <= limit:
 *      ZADD key score member (score = now, member = uuid)
 *      return allowed=true
 *    else:
 *      return allowed=false with resetMs = oldest remaining entry + windowMs
 */
export async function slidingWindowCheck(opts: SlidingWindowOpts): Promise<RateLimitResult> {
  const { limit, windowMs, key, cost = 1, failClosed = false } = opts;
  const now = Date.now();
  const windowStart = now - windowMs;

  try {
    await redis.zremrangebyscore(key, 0, windowStart);
    const currentCount = await redis.zcard(key);

    const count = typeof currentCount === "number" ? currentCount : 0;

    if (count + cost <= limit) {
      // Add this request to the window
      const member = `${now}-${Math.random().toString(36).slice(2, 8)}`;
      await redis.zadd(key, now, member);
      await redis.pexpire(key, windowMs);

      return {
        allowed: true,
        remaining: limit - count - cost,
        resetMs: now + windowMs,
        limit,
        windowMs,
      };
    }

    // Rejected — compute when the oldest entry in the window will expire
    const oldest = await redis.zrange(key, 0, 0, "WITHSCORES");
    const oldestTs = oldest.length >= 2 ? parseInt(oldest[1], 10) : windowStart;
    const resetMs = oldestTs + windowMs;

    slidingWindowRejectsTotal.inc({ route: key.split(":")[1] || "unknown" });

    return {
      allowed: false,
      remaining: 0,
      resetMs,
      limit,
      windowMs,
    };
  } catch (e) {
    logger.error({ err: e, key, failClosed }, "Sliding window rate limit check failed");
    // Fail-open by default for read-only/cheap endpoints; fail-closed for
    // expensive/mutating endpoints when requested.
    return { allowed: !failClosed, remaining: 0, resetMs: now, limit, windowMs };
  }
}

/**
 * Reset a sliding window key (useful for tests or admin ops).
 */
export async function resetSlidingWindow(key: string): Promise<void> {
  await redis.del(key);
}
