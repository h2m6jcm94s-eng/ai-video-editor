// Copyright (c) 2025 Devayan Dewri. All rights reserved.

// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { HeadBucketCommand } from "@aws-sdk/client-s3";
import { Connection } from "@temporalio/client";
import { sql } from "drizzle-orm";
import type { FastifyInstance } from "fastify";
import { db } from "../db";
import { env } from "../env";
import { sendError } from "../lib/errors";
import { redis } from "../lib/redis";
import { BUCKET, s3 } from "../services/storage";

const HEALTH_TIMEOUT_MS = 1_000;
const HEALTH_CACHE_TTL_MS = 5_000;

let cachedReady: { payload: unknown; at: number } | null = null;

async function withTimeout<T>(
  label: string,
  promise: Promise<T>,
): Promise<{ ok: true; latencyMs: number } | { ok: false; latencyMs: number; error: string }> {
  const start = performance.now();
  try {
    await Promise.race([
      promise,
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error(`${label} health check timed out`)), HEALTH_TIMEOUT_MS),
      ),
    ]);
    return { ok: true, latencyMs: Math.round(performance.now() - start) };
  } catch (err) {
    return {
      ok: false,
      latencyMs: Math.round(performance.now() - start),
      error: err instanceof Error ? err.message : `${label} unreachable`,
    };
  }
}

export async function healthRoutes(app: FastifyInstance) {
  app.get("/", async () => {
    return { status: "ok", timestamp: new Date().toISOString() };
  });

  app.get("/db", async (request, reply) => {
    try {
      await db.execute(sql`SELECT 1`);
      return { status: "ok", db: "connected" };
    } catch (e) {
      const message = e instanceof Error ? e.message : "Database unreachable";
      return sendError(reply, 503, message, "DB_UNAVAILABLE");
    }
  });

  app.get("/ready", { config: { rateLimit: { max: 12, timeWindow: "1 minute" } } }, async () => {
    const now = Date.now();
    if (process.env.NODE_ENV !== "test" && cachedReady && now - cachedReady.at < HEALTH_CACHE_TTL_MS) {
      return cachedReady.payload;
    }

    const [dbCheck, redisCheck, r2Check, temporalCheck] = await Promise.all([
      withTimeout("db", db.execute(sql`SELECT 1`)),
      withTimeout("redis", redis.ping()),
      withTimeout("r2", s3.send(new HeadBucketCommand({ Bucket: BUCKET }))),
      withTimeout(
        "temporal",
        Connection.connect({ address: env.TEMPORAL_HOST }).then((c) => c.close()),
      ),
    ]);

    const allOk = dbCheck.ok && redisCheck.ok && r2Check.ok && temporalCheck.ok;

    const payload = {
      status: allOk ? "ok" : "degraded",
      checks: {
        db: dbCheck,
        redis: redisCheck,
        r2: r2Check,
        temporal: temporalCheck,
      },
    };

    // Only cache healthy results. If the service is degraded we want the next
    // health probe to re-evaluate immediately rather than keep returning stale
    // "degraded" for the full TTL after recovery.
    if (allOk) {
      cachedReady = { payload, at: now };
    } else {
      cachedReady = null;
    }
    return payload;
  });
}
