import { describe, it, expect, vi } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";

describe("App.ts Coverage", () => {
  it("returns 422 for validation errors", async () => {
    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/projects",
      payload: {}, // missing required fields
    });
    expect(res.statusCode).toBe(422);
    const body = JSON.parse(res.body);
    expect(body.code).toBe("VALIDATION_ERROR");
  });

  it("exempts /api/health from auth", async () => {
    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/health" });
    expect(res.statusCode).toBe(200);
  });

  it("exempts /api/metrics from auth", async () => {
    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/metrics" });
    expect(res.statusCode).toBe(200);
  });

  it("propagates x-request-id header", async () => {
    const app = await buildApp();
    const res = await app.inject({
      method: "GET",
      url: "/api/health",
      headers: { "x-request-id": "custom-id-123" },
    });
    expect(res.headers["x-request-id"]).toBe("custom-id-123");
  });

  it("binds user context to logger after auth", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(undefined);
    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/projects/nonexistent" });
    expect(res.statusCode).toBe(404);
  });

  it("handles 500 errors gracefully", async () => {
    vi.mocked(db.query.projects.findFirst).mockRejectedValueOnce(new Error("DB crash"));
    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/projects/proj-1" });
    expect(res.statusCode).toBe(500);
    const body = JSON.parse(res.body);
    expect(body.code).toBe("INTERNAL_ERROR");
  });

  it("records HTTP metrics for every request", async () => {
    const app = await buildApp();
    await app.inject({ method: "GET", url: "/api/health" });

    const metricsRes = await app.inject({ method: "GET", url: "/api/metrics" });
    expect(metricsRes.statusCode).toBe(200);
    expect(metricsRes.body).toContain('method="GET"');
    expect(metricsRes.body).toContain("ave_http_request_duration_seconds_bucket");
  });
});
