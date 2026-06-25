// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
/**
 * Middleware to validate internal API token.
 * Used for worker → API communication.
 */

import type { FastifyReply, FastifyRequest } from "fastify";
import { env } from "../env";
import { sendError } from "../lib/errors";

export async function requireInternalToken(request: FastifyRequest, reply: FastifyReply): Promise<void> {
  // Read the token at request time so config changes do not require a restart.
  const internalToken = process.env.INTERNAL_WORKER_TOKEN;
  const token = request.headers["x-internal-token"];

  if (!internalToken) {
    request.log.error("INTERNAL_WORKER_TOKEN not configured");
    return sendError(reply, 500, "Internal token not configured", "INTERNAL_ERROR");
  }

  if (token !== internalToken) {
    request.log.warn({ ip: request.ip }, "Invalid internal token");
    return sendError(reply, 401, "Invalid internal token", "UNAUTHORIZED");
  }
}
