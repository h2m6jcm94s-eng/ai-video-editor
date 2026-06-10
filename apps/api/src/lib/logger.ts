// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
/**
 * Centralized logger configuration for the API.
 *
 * Features:
 * - Structured JSON logging in production
 * - Pretty printing in development and test
 * - Automatic redaction of sensitive fields
 * - Request correlation ID support
 */

import type { FastifyRequest, RawRequestDefaultExpression } from "fastify";
import pino from "pino";

/**
 * Module-level logger for service files that don't have request context.
 */
export const logger = pino({
  level: process.env.LOG_LEVEL || "info",
  ...(process.env.NODE_ENV === "production"
    ? {}
    : {
        transport: {
          target: "pino-pretty",
          options: {
            colorize: true,
            translateTime: "HH:MM:ss.l",
            ignore: "pid,hostname",
          },
        },
      }),
});

const REDACTED_FIELDS = [
  "encryptedKey",
  "authorization",
  "apiKey",
  "password",
  "token",
  "secret",
  "cookie",
  "x-api-key",
  "x-clerk-auth",
];

/**
 * Build Pino logger options based on environment.
 */
export function getLoggerConfig() {
  const isProduction = process.env.NODE_ENV === "production";
  const level = process.env.LOG_LEVEL || "info";

  return {
    level,
    redact: {
      paths: REDACTED_FIELDS.map((f) => `req.headers.${f}`),
      censor: "[REDACTED]",
    },
    ...(isProduction
      ? {}
      : {
          transport: {
            target: "pino-pretty",
            options: {
              colorize: true,
              translateTime: "HH:MM:ss.l",
              ignore: "pid,hostname",
            },
          },
        }),
  };
}

/**
 * Generate a request ID. Respects client-provided x-request-id or x-correlation-id.
 * Accepts either a FastifyRequest or raw IncomingMessage (from genReqId hook).
 */
export function generateRequestId(request?: FastifyRequest | RawRequestDefaultExpression): string {
  if (request) {
    const headers = (request as any).headers || {};
    const clientId = headers["x-request-id"] || headers["x-correlation-id"];
    if (typeof clientId === "string" && clientId.length > 0) {
      return clientId;
    }
  }
  return `req_${crypto.randomUUID().slice(0, 8)}`;
}

/**
 * Build request logger context with user and route info.
 */
export function buildRequestContext(request: FastifyRequest): Record<string, unknown> {
  const ctx: Record<string, unknown> = {
    route: request.routeOptions?.url || request.url,
    method: request.method,
    ip: request.ip,
  };

  if (request.userId) {
    ctx.userId = request.userId;
  }

  if (request.auth?.userId) {
    ctx.clerkId = request.auth.userId;
  }

  return ctx;
}
