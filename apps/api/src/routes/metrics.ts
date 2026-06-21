// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
/**
 * Prometheus metrics exposition endpoint.
 *
 * GET /api/metrics returns metrics in Prometheus text format.
 * Protected by METRICS_AUTH_TOKEN (bypassed in test mode).
 */

import { FastifyInstance } from "fastify";
import { sendError } from "../lib/errors";
import { getMetrics } from "../lib/metrics";

export async function metricsRoutes(app: FastifyInstance) {
  app.get("/", async (request, reply) => {
    // Always allow metrics in test mode; otherwise fail closed if no token is set.
    if (process.env.NODE_ENV === "test") {
      const metrics = await getMetrics();
      reply.header("Content-Type", "text/plain; version=0.0.4; charset=utf-8");
      return reply.send(metrics);
    }

    const token = process.env.METRICS_AUTH_TOKEN;
    if (!token) {
      return sendError(reply, 401, "Metrics auth not configured", "UNAUTHORIZED");
    }

    const authHeader = request.headers.authorization || "";
    const bearer = authHeader.replace(/^Bearer\s+/i, "");
    if (bearer !== token) {
      return sendError(reply, 401, "Unauthorized", "UNAUTHORIZED");
    }

    const metrics = await getMetrics();
    reply.header("Content-Type", "text/plain; version=0.0.4; charset=utf-8");
    return reply.send(metrics);
  });
}
