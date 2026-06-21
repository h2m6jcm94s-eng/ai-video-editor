import { afterEach, describe, expect, it, vi } from "vitest";
import { buildApp } from "../app";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("Metrics Endpoint", () => {
  it("GET /api/metrics returns Prometheus exposition format in test mode", async () => {
    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/metrics" });
    expect(res.statusCode).toBe(200);
    expect(res.headers["content-type"]).toContain("text/plain");
    expect(typeof res.body).toBe("string");
  });

  it("GET /api/metrics requires auth token in non-test mode when token is set", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("METRICS_AUTH_TOKEN", "secret-token-123");

    vi.resetModules();
    const { metricsRoutes } = await import("../routes/metrics");
    const fastify = await import("fastify");
    const testApp = fastify.default({ logger: false });
    await testApp.register(metricsRoutes, { prefix: "/api/metrics" });

    // No auth header
    const res1 = await testApp.inject({ method: "GET", url: "/api/metrics" });
    expect(res1.statusCode).toBe(401);
    const body1 = JSON.parse(res1.body);
    expect(body1.error).toBe("Unauthorized");

    // Wrong token
    const res2 = await testApp.inject({
      method: "GET",
      url: "/api/metrics",
      headers: { authorization: "Bearer wrong-token" },
    });
    expect(res2.statusCode).toBe(401);

    // Correct token
    const res3 = await testApp.inject({
      method: "GET",
      url: "/api/metrics",
      headers: { authorization: "Bearer secret-token-123" },
    });
    expect(res3.statusCode).toBe(200);
  });

  it("GET /api/metrics fails closed when METRICS_AUTH_TOKEN is empty", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("METRICS_AUTH_TOKEN", "");

    vi.resetModules();
    const { metricsRoutes } = await import("../routes/metrics");
    const fastify = await import("fastify");
    const testApp = fastify.default({ logger: false });
    await testApp.register(metricsRoutes, { prefix: "/api/metrics" });

    const res = await testApp.inject({ method: "GET", url: "/api/metrics" });
    expect(res.statusCode).toBe(401);
    expect(JSON.parse(res.body).code).toBe("UNAUTHORIZED");
  });
});

describe("HTTP Metrics Instrumentation", () => {
  it("records request metrics on every HTTP request", async () => {
    const app = await buildApp();

    const res = await app.inject({ method: "GET", url: "/api/health" });
    expect(res.statusCode).toBe(200);

    const metricsRes = await app.inject({ method: "GET", url: "/api/metrics" });
    expect(metricsRes.statusCode).toBe(200);
    expect(metricsRes.body).toContain("ave_http_requests_total");
    expect(metricsRes.body).toContain('method="GET"');
  });

  it("records duration histogram on HTTP requests", async () => {
    const app = await buildApp();

    await app.inject({ method: "GET", url: "/api/health" });

    const metricsRes = await app.inject({ method: "GET", url: "/api/metrics" });
    expect(metricsRes.body).toContain("ave_http_request_duration_seconds");
    expect(metricsRes.body).toContain("ave_http_request_duration_seconds_bucket");
    expect(metricsRes.body).toContain("ave_http_request_duration_seconds_sum");
    expect(metricsRes.body).toContain("ave_http_request_duration_seconds_count");
  });
});

describe("normalizeRoutePath", () => {
  it("replaces UUIDs with :id", async () => {
    const { normalizeRoutePath } = await import("../lib/metrics");
    const path = normalizeRoutePath("/api/projects/550e8400-e29b-41d4-a716-446655440000");
    expect(path).toBe("/api/projects/:id");
  });

  it("replaces numeric IDs with :id", async () => {
    const { normalizeRoutePath } = await import("../lib/metrics");
    const path = normalizeRoutePath("/api/items/12345");
    expect(path).toBe("/api/items/:id");
  });

  it("leaves static paths unchanged", async () => {
    const { normalizeRoutePath } = await import("../lib/metrics");
    const path = normalizeRoutePath("/api/health");
    expect(path).toBe("/api/health");
  });

  it("handles paths with multiple IDs", async () => {
    const { normalizeRoutePath } = await import("../lib/metrics");
    const path = normalizeRoutePath("/api/projects/123/assets/456");
    expect(path).toBe("/api/projects/:id/assets/:id");
  });
});
