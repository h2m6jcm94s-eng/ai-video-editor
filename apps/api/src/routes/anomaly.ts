// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import type { FastifyInstance } from "fastify";
import { sendError } from "../lib/errors";
import { listRecentAnomalies } from "../services/anomaly";

export async function anomalyRoutes(app: FastifyInstance) {
  app.get("/", async (request, reply) => {
    // Admin-only endpoint
    if (!request.userId) {
      return sendError(reply, 401, "Unauthorized", "UNAUTHORIZED");
    }

    const anomalies = await listRecentAnomalies();
    return { anomalies };
  });
}
