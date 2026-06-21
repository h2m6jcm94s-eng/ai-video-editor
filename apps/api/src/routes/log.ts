// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.

import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { sendError } from "../lib/errors";
import { requireAuth } from "../middleware/auth";

const logEventSchema = z
  .object({
    level: z.enum(["debug", "info", "warn", "error"]),
    message: z.string().max(2000),
    context: z.record(z.unknown()).optional(),
    ts: z.number(),
    url: z.string().max(500),
  })
  .strict();

const batchSchema = z
  .object({
    events: z.array(logEventSchema).max(100),
  })
  .strict();

export async function logRoutes(app: FastifyInstance) {
  app.post(
    "/api/log",
    {
      preHandler: [requireAuth],
      bodyLimit: 256 * 1024,
      config: {
        rateLimit: { max: 60, timeWindow: "1 minute" },
      },
    },
    async (request, reply) => {
      const result = batchSchema.safeParse(request.body);
      if (!result.success) {
        return sendError(reply, 422, "Validation failed", "VALIDATION_ERROR", result.error.issues);
      }
      const body = result.data;
      for (const ev of body.events) {
        request.log[ev.level](
          {
            source: "frontend",
            userId: request.userId,
            ...ev.context,
            url: ev.url,
            clientTs: ev.ts,
          },
          ev.message,
        );
      }
      return { ok: true };
    },
  );
}
