// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import "./env";
import { type ApiErrorCode, isApiErrorCode } from "@ai-video-editor/shared-types";
import cors from "@fastify/cors";
import multipart from "@fastify/multipart";
import rateLimit from "@fastify/rate-limit";
import Fastify from "fastify";
import fs from "fs";
import path from "path";
import { sendError } from "./lib/errors";
import { buildRequestContext, generateRequestId, getLoggerConfig } from "./lib/logger";
import {
  httpRequestDurationSeconds,
  httpRequestsTotal,
  normalizeRoutePath,
  rateLimitHitsTotal,
} from "./lib/metrics";
import { requireAuth } from "./middleware/auth";
import { adminRoutes } from "./routes/admin";
import { anomalyRoutes } from "./routes/anomaly";
import { billingRoutes } from "./routes/billing";
import { commandRoutes } from "./routes/commands";
import { healthRoutes } from "./routes/health";
import { internalRoutes } from "./routes/internal";
import { logRoutes } from "./routes/log";
import { metricsRoutes } from "./routes/metrics";
import { notificationRoutes } from "./routes/notifications";
import { presenceRoutes } from "./routes/presence";
import { progressRoutes } from "./routes/progress";
import { projectRoutes } from "./routes/projects";
import { renderRoutes } from "./routes/renders";
import { segmentRoutes } from "./routes/segments";
import { settingsRoutes } from "./routes/settings";
import { tasteRoutes } from "./routes/taste";
import { templateRoutes } from "./routes/templates";
import { uploadRoutes } from "./routes/uploads";
import { recordMetric } from "./services/anomaly";

export async function buildApp() {
  const app = Fastify({
    logger: getLoggerConfig(),
    bodyLimit: 1024 * 1024 * 1024,
    genReqId: (req) => generateRequestId(req),
  });

  app.setErrorHandler((error, request, reply) => {
    request.log.error({ err: error, statusCode: error.statusCode || 500 }, "Request error");

    if (error.validation) {
      return sendError(reply, 422, "Validation failed", "VALIDATION_ERROR", error.validation);
    }

    const isClientError = (error.statusCode ?? 500) < 500;
    const errorCode: ApiErrorCode = isApiErrorCode(error.code) ? error.code : "INTERNAL_ERROR";
    return sendError(
      reply,
      error.statusCode || 500,
      isClientError ? error.message : "Internal server error",
      errorCode,
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

  if (process.env.E2E !== "1") {
    await app.register(rateLimit, {
      max: process.env.NODE_ENV === "test" ? 10000 : 60,
      timeWindow: "1 minute",
      keyGenerator: (req) => req.userId ?? req.ip,
      onExceeded: async (req) => {
        const route = normalizeRoutePath(req.url);
        rateLimitHitsTotal.inc({ route });
        req.log.warn({ route }, "Rate limit exceeded");
      },
    });
  }

  // Request timing: track slow endpoints
  const SLOW_REQUEST_MS = 500;
  app.addHook("onRequest", async (request) => {
    request._startTime = performance.now();
  });
  app.addHook("onResponse", async (request, reply) => {
    const start = request._startTime;
    if (start !== undefined) {
      const durationMs = Math.round(performance.now() - start);
      const durationSec = durationMs / 1000;
      reply.header("x-response-time", `${durationMs}ms`);
      const statusCode = reply.statusCode;
      const route = normalizeRoutePath(request.routeOptions?.url || request.url);
      const method = request.method;
      const logData = {
        statusCode,
        duration: durationMs,
        route: request.routeOptions?.url || request.url,
      };

      // Record Prometheus metrics
      httpRequestsTotal.inc({ method, route, status_code: String(statusCode) });
      httpRequestDurationSeconds.observe({ method, route }, durationSec);

      if (durationMs > SLOW_REQUEST_MS) {
        request.log.warn(logData, "Slow request detected");
      } else if (statusCode >= 400) {
        request.log.warn(logData, "Request completed with error status");
      } else {
        request.log.info(logData, "Request completed");
      }
    }
  });

  // Propagate request ID via response header
  app.addHook("onSend", async (request, reply, payload) => {
    reply.header("x-request-id", request.id);
    return payload;
  });

  // Bind user context to request logger after auth
  app.addHook("onRequest", async (request) => {
    if (request.userId) {
      request.log = request.log.child(buildRequestContext(request));
    }
  });

  await app.register(healthRoutes, { prefix: "/api/health" });
  await app.register(metricsRoutes, { prefix: "/api/metrics" });
  await app.register(internalRoutes);
  await app.register(logRoutes);

  // Serve files from the configured local storage root. This makes local-disk
  // assets accessible to the web frontend without needing presigned R2 URLs.
  app.get("/storage/*", async (request, reply) => {
    const key = (request.params as Record<string, string>)["*"];
    const storageRoot = process.env.STORAGE_ROOT || "E:\\ai-video-editor-storage";
    const resolvedRoot = path.resolve(storageRoot);
    const filePath = path.resolve(path.join(resolvedRoot, key));

    if (filePath !== resolvedRoot && !filePath.startsWith(resolvedRoot + path.sep)) {
      return reply.status(403).send({ error: "Forbidden" });
    }
    if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
      return reply.status(404).send({ error: "Not found" });
    }
    return reply.send(fs.createReadStream(filePath));
  });

  app.addHook("onRequest", async (request, reply) => {
    if (request.url === "/api/health" || request.url.startsWith("/api/health/")) {
      return;
    }
    if (request.url === "/api/metrics" || request.url.startsWith("/api/metrics/")) {
      return;
    }
    if (request.url === "/api/internal" || request.url.startsWith("/api/internal/")) {
      return;
    }
    if (request.url === "/api/billing/webhook") {
      return;
    }
    await requireAuth(request, reply);
  });

  await app.register(billingRoutes, { prefix: "/api/billing" });
  await app.register(commandRoutes, { prefix: "/api" });
  await app.register(projectRoutes, { prefix: "/api/projects" });
  await app.register(uploadRoutes, { prefix: "/api/uploads" });
  await app.register(renderRoutes, { prefix: "/api/renders" });
  await app.register(segmentRoutes, { prefix: "/api/segments" });
  await app.register(progressRoutes, { prefix: "/api/progress" });
  await app.register(templateRoutes, { prefix: "/api/templates" });
  await app.register(presenceRoutes, { prefix: "/api/presence" });
  await app.register(settingsRoutes, { prefix: "/api/settings" });
  await app.register(tasteRoutes, { prefix: "/api/user-taste-profile" });
  await app.register(notificationRoutes, { prefix: "/api/notifications" });
  await app.register(adminRoutes, { prefix: "/api/admin" });
  await app.register(anomalyRoutes, { prefix: "/api/anomalies" });

  // Anomaly tracking: flag users with unusual request velocity
  app.addHook("onResponse", async (request, reply) => {
    const userId = request.userId;
    if (!userId || process.env.NODE_ENV === "test") return;

    const route = normalizeRoutePath(request.routeOptions?.url || request.url);

    // Fire-and-forget anomaly detection
    recordMetric(userId, `req:${route}`, 1).catch(() => {
      // silently ignore — anomaly detection must not break responses
    });

    if (reply.statusCode >= 500) {
      recordMetric(userId, "error_rate", 1).catch(() => {});
    }
  });

  return app;
}
