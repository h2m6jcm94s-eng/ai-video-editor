import { beforeEach, describe, expect, it, vi } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";

describe("Render completion webhook", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(db.query.projects.findFirst).mockResolvedValue(mockProject as any);
  });

  const mockRender = {
    id: "job-1",
    projectId: "proj-1",
    status: "running",
    outputAssetId: null,
    previewAssetId: null,
    errorMessage: null,
    completedAt: null,
  };

  const mockProject = {
    id: "proj-1",
    userId: "test-user-id",
    name: "Test",
    status: "rendering",
  };

  it("POST /api/renders/:jobId/complete marks job and project complete", async () => {
    vi.mocked(db.query.renders.findFirst).mockResolvedValueOnce(mockRender);

    const returningMock = vi
      .fn()
      .mockResolvedValue([
        { ...mockRender, status: "complete", outputAssetId: "550e8400-e29b-41d4-a716-446655440001" },
      ]);
    const whereMock = vi.fn().mockReturnValue({ returning: returningMock });
    const setMock = vi.fn().mockReturnValue({ where: whereMock });
    vi.mocked(db.update).mockReturnValue({ set: setMock } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/renders/job-1/complete",
      payload: { status: "complete", outputAssetId: "550e8400-e29b-41d4-a716-446655440001" },
      headers: { "x-internal-token": "test-internal-token-1234567890abcdef" },
    });

    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.job.status).toBe("complete");
  });

  it("POST /api/renders/:jobId/complete rejects invalid status", async () => {
    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/renders/job-1/complete",
      payload: { status: "unknown" },
      headers: { "x-internal-token": "test-internal-token-1234567890abcdef" },
    });
    expect(res.statusCode).toBe(422);
    expect(JSON.parse(res.body).code).toBe("VALIDATION_ERROR");
  });

  it("POST /api/renders/:jobId/complete returns 401 without x-internal-token", async () => {
    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/renders/job-1/complete",
      payload: { status: "complete" },
    });
    expect(res.statusCode).toBe(401);
    expect(JSON.parse(res.body).code).toBe("UNAUTHORIZED");
  });

  it("POST /api/renders/:jobId/complete returns 401 with wrong x-internal-token", async () => {
    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/renders/job-1/complete",
      payload: { status: "complete" },
      headers: { "x-internal-token": "bad-token" },
    });
    expect(res.statusCode).toBe(401);
    expect(JSON.parse(res.body).code).toBe("UNAUTHORIZED");
  });

  it("POST /api/renders/:jobId/complete returns 404 for missing render", async () => {
    vi.mocked(db.query.renders.findFirst).mockResolvedValueOnce(undefined);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/renders/job-1/complete",
      payload: { status: "complete" },
      headers: { "x-internal-token": "test-internal-token-1234567890abcdef" },
    });
    expect(res.statusCode).toBe(404);
  });

  it("POST /api/renders/:jobId/complete returns 404 when project is missing", async () => {
    vi.mocked(db.query.renders.findFirst).mockResolvedValueOnce(mockRender);
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(undefined);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/renders/job-1/complete",
      payload: { status: "complete" },
      headers: { "x-internal-token": "test-internal-token-1234567890abcdef" },
    });
    expect(res.statusCode).toBe(404);
  });

  it("POST /api/renders/:jobId/complete marks project failed on failed status", async () => {
    vi.mocked(db.query.renders.findFirst).mockResolvedValueOnce(mockRender);

    const returningMock = vi
      .fn()
      .mockResolvedValue([{ ...mockRender, status: "failed", errorMessage: "Encoder error" }]);
    const whereMock = vi.fn().mockReturnValue({ returning: returningMock });
    const setMock = vi.fn().mockReturnValue({ where: whereMock });
    vi.mocked(db.update).mockReturnValue({ set: setMock } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/renders/job-1/complete",
      payload: { status: "failed", errorMessage: "Encoder error" },
      headers: { "x-internal-token": "test-internal-token-1234567890abcdef" },
    });

    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.job.status).toBe("failed");
  });
});
