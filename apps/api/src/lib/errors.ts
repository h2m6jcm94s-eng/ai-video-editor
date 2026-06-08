// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import type { FastifyReply } from "fastify";

export interface ApiError {
  error: string;
  code: string;
  details?: unknown;
}

export function sendError(
  reply: FastifyReply,
  status: number,
  error: string,
  code: string,
  details?: unknown
) {
  const payload: ApiError = { error, code };
  if (details !== undefined) payload.details = details;
  return reply.status(status).send(payload);
}
