// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { redis } from "./redis";
import { cacheOperationsTotal } from "./metrics";

const DEFAULT_TTL_SECONDS = 30;

export async function cacheGet<T>(key: string): Promise<T | null> {
  const raw = await redis.get(key);
  if (!raw) {
    cacheOperationsTotal.inc({ operation: "get", result: "miss" });
    return null;
  }
  try {
    cacheOperationsTotal.inc({ operation: "get", result: "hit" });
    return JSON.parse(raw) as T;
  } catch {
    cacheOperationsTotal.inc({ operation: "get", result: "miss" });
    return null;
  }
}

export async function cacheSet(key: string, value: unknown, ttlSeconds = DEFAULT_TTL_SECONDS): Promise<void> {
  await redis.setex(key, ttlSeconds, JSON.stringify(value));
  cacheOperationsTotal.inc({ operation: "set", result: "success" });
}

export async function cacheDel(key: string): Promise<void> {
  await redis.del(key);
  cacheOperationsTotal.inc({ operation: "del", result: "success" });
}

export async function cacheInvalidatePattern(pattern: string): Promise<void> {
  const keys = await redis.keys(pattern);
  if (keys.length > 0) {
    await redis.del(...keys);
  }
  cacheOperationsTotal.inc({ operation: "invalidate", result: "success" });
}
