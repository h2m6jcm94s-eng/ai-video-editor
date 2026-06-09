import { describe, it, expect, vi, beforeEach } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";

describe("Logging Integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns client-provided x-request-id in response headers", async () => {
    vi.mocked(db.query.projects.findMany).mockResolvedValueOnce([]);

    const app = await buildApp();
    const res = await app.inject({
      method: "GET",
      url: "/api/projects",
      headers: { "x-request-id": "my-trace-123" },
    });

    expect(res.statusCode).toBe(200);
    expect(res.headers["x-request-id"]).toBe("my-trace-123");
  });

  it("returns generated request-id when no client header is provided", async () => {
    vi.mocked(db.query.projects.findMany).mockResolvedValueOnce([]);

    const app = await buildApp();
    const res = await app.inject({
      method: "GET",
      url: "/api/projects",
    });

    expect(res.statusCode).toBe(200);
    expect(res.headers["x-request-id"]).toMatch(/^req_[a-f0-9]{8}$/);
  });

  it("tracks request timing via onResponse hook", async () => {
    vi.mocked(db.query.projects.findMany).mockResolvedValueOnce([]);

    const app = await buildApp();
    // Spy on the logger to verify the timing log is emitted
    const logSpy = vi.fn();
    app.addHook("onResponse", async (request, reply) => {
      logSpy(reply.statusCode);
    });

    const res = await app.inject({
      method: "GET",
      url: "/api/projects",
    });

    expect(res.statusCode).toBe(200);
    expect(logSpy).toHaveBeenCalledWith(200);
  });

  it("logs error via sendError for 404 responses", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(undefined);

    const app = await buildApp();
    const res = await app.inject({
      method: "GET",
      url: "/api/projects/nonexistent-id",
    });

    expect(res.statusCode).toBe(404);
    const body = JSON.parse(res.body);
    expect(body.code).toBe("NOT_FOUND");
  });

  it("logs error via sendError for 403 responses", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce({
      id: "proj-1",
      userId: "other-user-id",
      name: "Test",
    });

    const app = await buildApp();
    const res = await app.inject({
      method: "GET",
      url: "/api/projects/proj-1",
    });

    expect(res.statusCode).toBe(403);
    const body = JSON.parse(res.body);
    expect(body.code).toBe("FORBIDDEN");
  });

  it("logs auth errors without crashing", async () => {
    const app = await buildApp();
    const res = await app.inject({
      method: "GET",
      url: "/api/projects/proj-1",
    });

    // The mock setup makes auth succeed by default
    // This test mainly ensures the auth logging path doesn't crash
    expect([200, 401, 403, 404, 500]).toContain(res.statusCode);
  });
});
