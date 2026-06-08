// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { FastifyInstance } from "fastify";
import { sql } from "drizzle-orm";
import { db } from "../db";
import { sendError } from "../lib/errors";

export async function healthRoutes(app: FastifyInstance) {
  app.get("/", async () => {
    return { status: "ok", timestamp: new Date().toISOString() };
  });

  app.get("/db", async (request, reply) => {
    try {
      await db.execute(sql`SELECT 1`);
      return { status: "ok", db: "connected" };
    } catch (e: any) {
      return sendError(reply, 503, e.message || "Database unreachable", "DB_UNAVAILABLE");
    }
  });
}
