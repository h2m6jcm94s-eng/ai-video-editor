// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.

import type { ApiErrorCode } from "@ai-video-editor/shared-types";
import type { FastifyReply } from "fastify";
import { recordUserEvent } from "./userEvents";

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
  details?: unknown,
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

    // Persist per-user error event (fire-and-forget)
    const userId = req?.user?.id as string | undefined;
    if (userId) {
      recordUserEvent({
        userId,
        code,
        message: error,
        details,
        route: req?.routeOptions?.url ?? req?.url,
      }).catch(() => {
        // Swallow — event recording must not break the response
      });
    }
  } catch {
    // If logging fails, don't block the error response
  }

  const payload: ApiError = { error, code };
  if (details !== undefined) payload.details = details;
  return reply.status(status).send(payload);
}
