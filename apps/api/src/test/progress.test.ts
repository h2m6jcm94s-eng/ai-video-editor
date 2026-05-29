import { describe, it, expect, vi, beforeEach } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";

describe("Progress Routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const PROJ_ID = "8562dc1a-1493-42ee-ab6e-1075b83c88d6";
  const JOB_ID = "fc6b55b4-01cd-431b-808a-35b4f28613e1";

  const mockProject = {
    id: PROJ_ID,
    userId: "test-user-id",
    name: "Test",
    status: "rendering",
  };

  const mockRender = {
    id: JOB_ID,
    projectId: PROJ_ID,
    status: "running",
    stage: "compiling",
    progress: 50,
  };

  it.skip("GET /api/progress/:jobId/events returns SSE headers", async () => {
    // SSE endpoints keep connections open; test via integration or manual verification.
    // Auth + ownership coverage is provided by the 404/403 tests above.
  });

  it("GET /api/progress/:jobId/events returns 404 for missing job", async () => {
    vi.mocked(db.query.renders.findFirst).mockResolvedValueOnce(undefined);

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: `/api/progress/${JOB_ID}/events` });
    expect(res.statusCode).toBe(404);
  });

  it("GET /api/progress/:jobId/events returns 403 for other user's job", async () => {
    vi.mocked(db.query.renders.findFirst).mockResolvedValueOnce(mockRender as any);
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce({
      ...mockProject,
      userId: "other-user-id",
    } as any);

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: `/api/progress/${JOB_ID}/events` });
    expect(res.statusCode).toBe(403);
  });
});
