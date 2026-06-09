import { describe, it, expect, vi, beforeEach } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";

describe("Progress Routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockRender = {
    id: "render-1",
    projectId: "proj-1",
    status: "running",
    workflowId: "wf-1",
    createdAt: new Date(),
    updatedAt: new Date(),
  };

  const mockProject = {
    id: "proj-1",
    userId: "test-user-id",
    name: "Test Project",
  };

  it("GET /api/progress/:jobId/events returns 404 when job not found", async () => {
    vi.mocked(db.query.renders.findFirst).mockResolvedValueOnce(undefined);

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/progress/render-999/events" });
    expect(res.statusCode).toBe(404);
    expect(JSON.parse(res.body).code).toBe("NOT_FOUND");
  });

  it("GET /api/progress/:jobId/events returns 403 when job belongs to another user", async () => {
    vi.mocked(db.query.renders.findFirst).mockResolvedValueOnce({
      ...mockRender,
      project: { ...mockProject, userId: "other-user-id" },
    });

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/progress/render-1/events" });
    expect(res.statusCode).toBe(403);
    expect(JSON.parse(res.body).code).toBe("FORBIDDEN");
  });

  it("GET /api/progress/:jobId/events returns 403 when project is missing", async () => {
    vi.mocked(db.query.renders.findFirst).mockResolvedValueOnce({
      ...mockRender,
      project: null,
    });

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/progress/render-1/events" });
    expect(res.statusCode).toBe(403);
    expect(JSON.parse(res.body).code).toBe("FORBIDDEN");
  });


});
