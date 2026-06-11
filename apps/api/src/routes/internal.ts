// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
/**
 * Internal routes for worker → API communication.
 * Protected by requireInternalToken.
 */

import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { recordUserEvent } from "../lib/userEvents";
import { requireInternalToken } from "../middleware/requireInternalToken";

const userEventSchema = z
  .object({
    userId: z.string().uuid(),
    code: z.string().min(1).max(50),
    message: z.string().min(1).max(2000),
    details: z.record(z.unknown()).optional(),
    route: z.string().max(255).optional(),
  })
  .strict();

export async function internalRoutes(app: FastifyInstance) {
  app.addHook("preHandler", requireInternalToken);

  app.post("/api/internal/user-events", async (request, reply) => {
    const body = userEventSchema.parse(request.body);
    await recordUserEvent(body);
    return { ok: true };
  });
}
