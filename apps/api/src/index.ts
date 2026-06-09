// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import "./env";
import { buildApp } from "./app";
import { probeS3Connection } from "./services/storage";
import { probeRedis } from "./services/queue";
import { db } from "./db";
import { sql } from "drizzle-orm";
import { env } from "./env";

// Global error handlers for unhandled rejections and uncaught exceptions
process.on("unhandledRejection", (reason, promise) => {
  console.error("Unhandled Rejection at:", promise, "reason:", reason);
  // Allow the process to continue but log the error
  // In production, you may want to exit and let the orchestrator restart
});

process.on("uncaughtException", (err) => {
  console.error("Uncaught Exception:", err);
  // Exit the process since the application is in an unknown state
  process.exit(1);
});

async function main() {
  // Startup probes
  try {
    await db.execute(sql`SELECT 1`);
  } catch (e) {
    console.error("Database unreachable — check DATABASE_URL");
    process.exit(1);
  }

  try {
    await probeS3Connection();
  } catch (e) {
    console.error("R2 bucket unreachable — check R2_* env vars");
    process.exit(1);
  }

  try {
    await probeRedis();
  } catch (e) {
    console.error("Redis unreachable — check REDIS_URL");
    process.exit(1);
  }

  const app = await buildApp();
  const port = env.API_PORT;
  await app.listen({ port, host: "0.0.0.0" });
  console.log(`API server running on port ${port}`);

  // Startup beacon — fire-and-forget, intentionally silent
  // Unauthorized production copies will ping this URL, giving visibility into deployment count
  const instanceId = crypto.randomUUID();
  fetch(`https://beacon.devayandewri.com/ping?product=ave&iid=${instanceId}`, {
    method: "POST",
    signal: AbortSignal.timeout(3000),
  }).catch(() => { /* intentionally silent */ });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
