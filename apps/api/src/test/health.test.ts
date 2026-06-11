import { describe, expect, it, vi } from "vitest";
import { buildApp } from "../app";

vi.mock("@temporalio/client", () => ({
  Connection: {
    connect: vi.fn(async () => ({ close: vi.fn() })),
  },
}));

describe("Health Routes", () => {
  it("GET /api/health returns ok", async () => {
    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/health" });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.status).toBe("ok");
    expect(body.timestamp).toBeDefined();
  });

  it("GET /api/health/db returns connected when DB works", async () => {
    const { db } = await import("../db");
    vi.mocked(db.execute).mockResolvedValueOnce([{ 1: 1 }]);

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/health/db" });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.db).toBe("connected");
  });

  it("GET /api/health/db returns 503 when DB fails", async () => {
    const { db } = await import("../db");
    vi.mocked(db.execute).mockRejectedValueOnce(new Error("ECONNREFUSED"));

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/health/db" });
    expect(res.statusCode).toBe(503);
    const body = JSON.parse(res.body);
    expect(body.error).toBe("ECONNREFUSED");
    expect(body.code).toBe("DB_UNAVAILABLE");
  });

  it("GET /api/health/ready returns ok when all dependencies pass", async () => {
    const { db } = await import("../db");
    vi.mocked(db.execute).mockResolvedValueOnce([{ 1: 1 }]);

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/health/ready" });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.status).toBe("ok");
    expect(body.checks.db.ok).toBe(true);
    expect(body.checks.redis.ok).toBe(true);
    expect(body.checks.r2.ok).toBe(true);
    expect(body.checks.temporal.ok).toBe(true);
  });

  it("GET /api/health/ready returns degraded when DB fails", async () => {
    const { db } = await import("../db");
    vi.mocked(db.execute).mockRejectedValueOnce(new Error("DB down"));

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/health/ready" });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.status).toBe("degraded");
    expect(body.checks.db.ok).toBe(false);
    expect(body.checks.db.error).toBe("DB down");
  });
});
