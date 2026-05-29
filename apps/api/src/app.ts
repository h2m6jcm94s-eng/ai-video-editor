import Fastify from "fastify";
import cors from "@fastify/cors";
import multipart from "@fastify/multipart";
import rateLimit from "@fastify/rate-limit";
import { projectRoutes } from "./routes/projects";
import { uploadRoutes } from "./routes/uploads";
import { renderRoutes } from "./routes/renders";
import { progressRoutes } from "./routes/progress";
import { healthRoutes } from "./routes/health";
import { requireAuth } from "./middleware/auth";

export async function buildApp() {
  const app = Fastify({
    logger: false,
    bodyLimit: 1024 * 1024 * 1024,
  });

  app.setErrorHandler((error, request, reply) => {
    app.log.error({ err: error, url: request.url }, "Request error");

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

  if (process.env.NODE_ENV !== "test") {
    await app.register(rateLimit, {
      max: 60,
      timeWindow: "1 minute",
      keyGenerator: (req) => req.userId ?? req.ip,
    });
  }

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

  return app;
}
