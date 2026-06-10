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
import { getMetrics } from "../lib/metrics";
import { sendError } from "../lib/errors";

export async function metricsRoutes(app: FastifyInstance) {
  app.get("/", async (request, reply) => {
    const token = process.env.METRICS_AUTH_TOKEN;
    // Skip auth in test mode or when no token is configured
    if (process.env.NODE_ENV !== "test" && token) {
      const authHeader = request.headers.authorization || "";
      const bearer = authHeader.replace(/^Bearer\s+/i, "");
      if (bearer !== token) {
        return sendError(reply, 401, "Unauthorized", "UNAUTHORIZED");
      }
    }

    const metrics = await getMetrics();
    reply.header("Content-Type", "text/plain; version=0.0.4; charset=utf-8");
    return reply.send(metrics);
  });
}
