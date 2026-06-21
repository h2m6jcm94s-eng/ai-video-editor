// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import type { FastifyInstance } from "fastify";
import { requireAdmin } from "../middleware/requireAdmin";
import { listRecentAnomalies } from "../services/anomaly";

export async function anomalyRoutes(app: FastifyInstance) {
  app.get("/", { preHandler: requireAdmin }, async () => {
    const anomalies = await listRecentAnomalies();
    return { anomalies };
  });
}
