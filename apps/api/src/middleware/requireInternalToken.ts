// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
/**
 * Middleware to validate internal API token.
 * Used for worker → API communication.
 */

import type { FastifyReply, FastifyRequest } from "fastify";
import { sendError } from "../lib/errors";

const INTERNAL_TOKEN = process.env.INTERNAL_API_TOKEN;

export async function requireInternalToken(request: FastifyRequest, reply: FastifyReply): Promise<void> {
  const token = request.headers["x-internal-token"];

  if (!INTERNAL_TOKEN) {
    request.log.error("INTERNAL_API_TOKEN not configured");
    return sendError(reply, 500, "Internal token not configured", "INTERNAL_ERROR");
  }

  if (token !== INTERNAL_TOKEN) {
    request.log.warn({ ip: request.ip }, "Invalid internal token");
    return sendError(reply, 401, "Invalid internal token", "UNAUTHORIZED");
  }
}
