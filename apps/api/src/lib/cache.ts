// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.

import { cacheOperationsTotal } from "./metrics";
import { redis } from "./redis";

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
  const stream = redis.scanStream({ match: pattern, count: 100 });
  const keys: string[] = [];

  return new Promise((resolve, reject) => {
    stream.on("data", (resultKeys: string[]) => {
      keys.push(...resultKeys);
    });

    stream.on("end", async () => {
      try {
        if (keys.length > 0) {
          await redis.del(...keys);
        }
        cacheOperationsTotal.inc({ operation: "invalidate", result: "success" });
        resolve();
      } catch (err) {
        cacheOperationsTotal.inc({ operation: "invalidate", result: "error" });
        reject(err);
      }
    });

    stream.on("error", (err) => {
      cacheOperationsTotal.inc({ operation: "invalidate", result: "error" });
      reject(err);
    });
  });
}
