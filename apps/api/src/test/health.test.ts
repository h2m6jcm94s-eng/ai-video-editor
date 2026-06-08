import { describe, it, expect, vi } from "vitest";
import { buildApp } from "../app";

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
});
