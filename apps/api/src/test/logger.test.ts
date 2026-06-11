import type { FastifyRequest } from "fastify";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { buildRequestContext, generateRequestId, getLoggerConfig } from "../lib/logger";

describe("Logger", () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
    vi.clearAllMocks();
  });

  describe("getLoggerConfig", () => {
    it("returns JSON config with Loki transport in production", () => {
      vi.stubEnv("NODE_ENV", "production");
      vi.stubEnv("LOG_LEVEL", "warn");
      const config = getLoggerConfig();
      expect(config.level).toBe("warn");
      expect(config.transport).toBeDefined();
      expect(config.transport).toHaveProperty("targets");
      const targets = (config.transport as { targets: unknown[] }).targets;
      expect(targets.some((t: unknown) => (t as { target: string }).target === "pino-loki")).toBe(true);
      expect(config.redact).toBeDefined();
      expect(config.redact!.paths).toContain("req.headers.encryptedKey");
    });

    it("returns pretty config in development", () => {
      vi.stubEnv("NODE_ENV", "development");
      const config = getLoggerConfig();
      expect(config.transport).toBeDefined();
      expect(config.transport).toHaveProperty("target", "pino-pretty");
    });

    it("returns pretty config in test", () => {
      vi.stubEnv("NODE_ENV", "test");
      const config = getLoggerConfig();
      expect(config.transport).toBeDefined();
      expect(config.transport).toHaveProperty("target", "pino-pretty");
    });

    it("defaults log level to info", () => {
      vi.stubEnv("NODE_ENV", "production");
      const config = getLoggerConfig();
      expect(config.level).toBe("info");
    });

    it("redacts sensitive headers", () => {
      vi.stubEnv("NODE_ENV", "production");
      const config = getLoggerConfig();
      const paths = config.redact!.paths as string[];
      expect(paths).toContain("req.headers.encryptedKey");
      expect(paths).toContain("req.headers.authorization");
      expect(paths).toContain("req.headers.apiKey");
      expect(paths).toContain("req.headers.password");
      expect(paths).toContain("req.headers.token");
      expect(paths).toContain("req.headers.secret");
      expect(paths).toContain('req.headers["x-internal-token"]');
      expect(paths).toContain("req.query.apiKey");
      expect(paths).toContain("req.query.key");
      expect(paths).toContain("req.body.encryptedKey");
      expect(paths).toContain("req.body.password");
      expect(paths).toContain('res.headers["set-cookie"]');
    });
  });

  describe("generateRequestId", () => {
    it("respects client-provided x-request-id", () => {
      const request = {
        headers: { "x-request-id": "client-trace-123" },
      } as unknown as FastifyRequest;
      expect(generateRequestId(request)).toBe("client-trace-123");
    });

    it("respects client-provided x-correlation-id", () => {
      const request = {
        headers: { "x-correlation-id": "corr-456" },
      } as unknown as FastifyRequest;
      expect(generateRequestId(request)).toBe("corr-456");
    });

    it("prefers x-request-id over x-correlation-id", () => {
      const request = {
        headers: { "x-request-id": "req-1", "x-correlation-id": "corr-2" },
      } as unknown as FastifyRequest;
      expect(generateRequestId(request)).toBe("req-1");
    });

    it("generates a new ID when no client header is provided", () => {
      const request = {
        headers: {},
      } as unknown as FastifyRequest;
      const id = generateRequestId(request);
      expect(id).toMatch(/^req_[a-f0-9]{8}$/);
    });

    it("generates a new ID when request is undefined", () => {
      const id = generateRequestId(undefined);
      expect(id).toMatch(/^req_[a-f0-9]{8}$/);
    });

    it("generates a new ID for empty string header", () => {
      const request = {
        headers: { "x-request-id": "" },
      } as unknown as FastifyRequest;
      const id = generateRequestId(request);
      expect(id).toMatch(/^req_[a-f0-9]{8}$/);
    });
  });

  describe("buildRequestContext", () => {
    it("builds context with route and method", () => {
      const request = {
        routeOptions: { url: "/api/projects" },
        method: "GET",
        ip: "127.0.0.1",
      } as unknown as FastifyRequest;
      const ctx = buildRequestContext(request);
      expect(ctx).toEqual({
        route: "/api/projects",
        method: "GET",
        ip: "127.0.0.1",
      });
    });

    it("includes userId when present", () => {
      const request = {
        routeOptions: { url: "/api/projects" },
        method: "GET",
        ip: "127.0.0.1",
        userId: "user-123",
      } as unknown as FastifyRequest;
      const ctx = buildRequestContext(request);
      expect(ctx.userId).toBe("user-123");
    });

    it("includes clerkId when auth is present", () => {
      const request = {
        routeOptions: { url: "/api/projects" },
        method: "GET",
        ip: "127.0.0.1",
        userId: "user-123",
        auth: { userId: "clerk_abc" },
      } as unknown as FastifyRequest;
      const ctx = buildRequestContext(request);
      expect(ctx.clerkId).toBe("clerk_abc");
    });

    it("falls back to url when routeOptions is missing", () => {
      const request = {
        url: "/api/projects",
        method: "GET",
        ip: "127.0.0.1",
      } as unknown as FastifyRequest;
      const ctx = buildRequestContext(request);
      expect(ctx.route).toBe("/api/projects");
    });
  });
});
