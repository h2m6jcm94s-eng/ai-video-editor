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

export async function buildApp() {
  const app = Fastify({
    logger: { level: process.env.LOG_LEVEL || "info" },
    bodyLimit: 1024 * 1024 * 1024,
    genReqId: () => `req_${crypto.randomUUID().slice(0, 8)}`,
  });

  app.setErrorHandler((error, request, reply) => {
    request.log.error({ err: error, url: request.url }, "Request error");

    if (error.validation) {
      return reply.status(422).send({
        error: "Validation failed",
        code: "VALIDATION_ERROR",
        details: error.validation,
      });
    }

    const isClientError = (error.statusCode ?? 500) < 500;
    return reply.status(error.statusCode || 500).send({
      error: isClientError ? error.message : "Internal server error",
      code: error.code || "INTERNAL_ERROR",
    });
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
