import { describe, it, expect, vi, beforeEach } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";

describe("Render completion webhook", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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

  it("POST /api/renders/:jobId/complete marks job and project complete", async () => {
    vi.mocked(db.query.renders.findFirst).mockResolvedValueOnce(mockRender);

    const returningMock = vi.fn().mockResolvedValue([{ ...mockRender, status: "complete", outputAssetId: "550e8400-e29b-41d4-a716-446655440001" }]);
    const whereMock = vi.fn().mockReturnValue({ returning: returningMock });
    const setMock = vi.fn().mockReturnValue({ where: whereMock });
    vi.mocked(db.update).mockReturnValue({ set: setMock } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/renders/job-1/complete",
      payload: { status: "complete", outputAssetId: "550e8400-e29b-41d4-a716-446655440001" },
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
    });
    expect(res.statusCode).toBe(422);
    expect(JSON.parse(res.body).code).toBe("VALIDATION_ERROR");
  });
});
