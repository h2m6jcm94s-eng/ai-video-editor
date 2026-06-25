// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import "./env";
import { sql } from "drizzle-orm";
import { buildApp } from "./app";
import { db } from "./db";
import { env } from "./env";
import { probeRedis } from "./services/queue";
import { probeS3Connection } from "./services/storage";

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

/** Best-effort cleanup of a previous dev server still holding `port`.
 *
 * This is only used in non-production environments to keep `tsx watch` and
 * `node --watch` restarts from failing with EADDRINUSE on Windows.
 */
async function killProcessOnPort(port: number): Promise<void> {
  const currentPid = process.pid;
  try {
    const { execSync } = await import("child_process");
    if (process.platform === "win32") {
      const output = execSync(`netstat -ano | findstr ":${port} "`, { encoding: "utf-8" });
      const pids = new Set<string>();
      for (const line of output.split("\n")) {
        const parts = line.trim().split(/\s+/);
        if (parts.length >= 5 && parts[1].includes(`:${port}`) && parts[3] === "LISTENING") {
          pids.add(parts[4]);
        }
      }
      if (pids.size > 0) {
        console.log(`[dev] cleaning up previous listeners on port ${port}: ${Array.from(pids).join(", ")}`);
      }
      for (const pid of pids) {
        if (Number(pid) === currentPid) continue;
        try {
          execSync(`taskkill /F /PID ${pid}`);
          console.log(`[dev] killed stale listener ${pid}`);
        } catch {
          // ignore: process may have exited between netstat and taskkill
        }
      }
    } else {
      try {
        const pid = execSync(`lsof -ti tcp:${port}`, { encoding: "utf-8" }).trim();
        if (pid && Number(pid) !== currentPid) {
          console.log(`[dev] cleaning up previous listener on port ${port}: ${pid}`);
          execSync(`kill -9 ${pid}`);
        }
      } catch {
        // ignore: nothing using the port
      }
    }
  } catch (err) {
    console.log(`[dev] port cleanup failed:`, (err as Error).message);
  }
}

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

  // Retry bind so dev watchers (tsx watch, node --watch) can restart on
  // Windows without EADDRINUSE. In non-production mode we also try to clean
  // up a lingering previous listener on each attempt.
  const maxBindRetries = 30;
  const bindRetryDelayMs = 300;
  for (let attempt = 1; attempt <= maxBindRetries; attempt++) {
    if (process.env.NODE_ENV !== "production") {
      await killProcessOnPort(port);
    }
    try {
      await app.listen({ port, host: "0.0.0.0" });
      break;
    } catch (err) {
      const isAddrInUse = (err as NodeJS.ErrnoException)?.code === "EADDRINUSE";
      if (!isAddrInUse || attempt === maxBindRetries) {
        throw err;
      }
      app.log.warn(`Port ${port} in use, retrying (${attempt}/${maxBindRetries})...`);
      await new Promise((resolve) => setTimeout(resolve, bindRetryDelayMs));
    }
  }
  app.log.info(`API server running on port ${port}`);

  // Graceful shutdown so dev watchers (tsx watch, nodemon, etc.) can restart
  // without EADDRINUSE from a lingering server socket.
  const closeServer = async (signal: string) => {
    app.log.info(`Received ${signal}, shutting down...`);
    try {
      await app.close();
      app.log.info("Server closed gracefully");
    } catch (err) {
      app.log.error({ err }, "Error during graceful shutdown");
    }
    process.exit(0);
  };

  process.on("SIGINT", () => closeServer("SIGINT"));
  process.on("SIGTERM", () => closeServer("SIGTERM"));

  // Startup beacon — fire-and-forget, intentionally silent
  // Unauthorized production copies will ping this URL, giving visibility into deployment count
  const instanceId = crypto.randomUUID();
  fetch(`https://beacon.devayandewri.com/ping?product=ave&iid=${instanceId}`, {
    method: "POST",
    signal: AbortSignal.timeout(3000),
  }).catch(() => {
    /* intentionally silent */
  });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
