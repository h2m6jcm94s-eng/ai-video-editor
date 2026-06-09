// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import type { FastifyReply } from "fastify";
import type { ApiErrorCode } from "@ai-video-editor/shared-types";

export interface ApiError {
  error: string;
  code: ApiErrorCode;
  details?: unknown;
}

export function sendError(
  reply: FastifyReply,
  status: number,
  error: string,
  code: ApiErrorCode,
  details?: unknown
) {
  // Log the error via the request logger if available
  try {
    const req = (reply as any).request;
    if (req?.log) {
      if (status >= 500) {
        req.log.error({ status, code, error, details }, "Error response sent");
      } else {
        req.log.warn({ status, code, error, details }, "Error response sent");
      }
    }
  } catch {
    // If logging fails, don't block the error response
  }

  const payload: ApiError = { error, code };
  if (details !== undefined) payload.details = details;
  return reply.status(status).send(payload);
}
