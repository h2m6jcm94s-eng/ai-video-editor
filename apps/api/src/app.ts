// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import Fastify from "fastify";
import cors from "@fastify/cors";
import multipart from "@fastify/multipart";
import rateLimit from "@fastify/rate-limit";
import { projectRoutes } from "./routes/projects";
import { uploadRoutes } from "./routes/uploads";
import { renderRoutes } from "./routes/renders";
import { progressRoutes } from "./routes/progress";
import { templateRoutes } from "./routes/templates";
import { presenceRoutes } from "./routes/presence";
import { settingsRoutes } from "./routes/settings";
import { healthRoutes } from "./routes/health";
import { requireAuth } from "./middleware/auth";
import { sendError } from "./lib/errors";

export async function buildApp() {
  const app = Fastify({
    logger: { level: process.env.LOG_LEVEL || "info" },
    bodyLimit: 1024 * 1024 * 1024,
    genReqId: () => `req_${crypto.randomUUID().slice(0, 8)}`,
  });

  app.setErrorHandler((error, request, reply) => {
    request.log.error({ err: error, url: request.url }, "Request error");

    if (error.validation) {
      return sendError(reply, 422, "Validation failed", "VALIDATION_ERROR", error.validation);
    }

    const isClientError = (error.statusCode ?? 500) < 500;
    return sendError(
      reply,
      error.statusCode || 500,
      isClientError ? error.message : "Internal server error",
      error.code || "INTERNAL_ERROR"
    );
  });

  await app.register(cors, {
    origin: process.env.WEB_URL || "http://localhost:3000",
    credentials: true,
  });

  await app.register(multipart, {
    limits: {
      fileSize: 1024 * 1024 * 1024 * 2,
      files: 30,
    },
  });

  await app.register(rateLimit, {
    max: process.env.NODE_ENV === "test" ? 10000 : 60,
    timeWindow: "1 minute",
    keyGenerator: (req) => req.userId ?? req.ip,
  });

  // Request timing: track slow endpoints
  const SLOW_REQUEST_MS = 500;
  app.addHook("onRequest", async (request) => {
    (request as any)._startTime = performance.now();
  });
  app.addHook("onResponse", async (request, reply) => {
    const start = (request as any)._startTime as number | undefined;
    if (start !== undefined) {
      const duration = Math.round(performance.now() - start);
      reply.header("x-response-time", `${duration}ms`);
      if (duration > SLOW_REQUEST_MS) {
        request.log.warn({ url: request.url, method: request.method, duration }, "Slow request detected");
      }
    }
  });

  // Propagate request ID via response header
  app.addHook("onSend", async (request, reply, payload) => {
    reply.header("x-request-id", request.id);
    return payload;
  });

  await app.register(healthRoutes, { prefix: "/api/health" });

  app.addHook("onRequest", async (request, reply) => {
    if (request.url === "/api/health" || request.url.startsWith("/api/health/")) {
      return;
    }
    await requireAuth(request, reply);
  });

  await app.register(projectRoutes, { prefix: "/api/projects" });
  await app.register(uploadRoutes, { prefix: "/api/uploads" });
  await app.register(renderRoutes, { prefix: "/api/renders" });
  await app.register(progressRoutes, { prefix: "/api/progress" });
  await app.register(templateRoutes, { prefix: "/api/templates" });
  await app.register(presenceRoutes, { prefix: "/api/presence" });
  await app.register(settingsRoutes, { prefix: "/api/settings" });

  return app;
}
