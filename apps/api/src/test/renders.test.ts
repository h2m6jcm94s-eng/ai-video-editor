import { describe, it, expect, vi, beforeEach } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";
import { startRenderWorkflow } from "../services/temporal";
import { enqueueJob } from "../services/queue";

describe("Render Routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const PROJ_ID = "8562dc1a-1493-42ee-ab6e-1075b83c88d6";
  const RENDER_ID = "fc6b55b4-01cd-431b-808a-35b4f28613e1";

  const mockProject = {
    id: PROJ_ID,
    userId: "test-user-id",
    name: "Test",
    status: "uploading",
    referenceAssetId: "ref-1",
    songAssetId: "song-1",
    clipAssetIds: [],
    styleTier: "full_style",
    mode: "auto",
  };

  const mockRender = {
    id: RENDER_ID,
    projectId: PROJ_ID,
    status: "queued",
    stage: "queued",
    progress: 0,
    workflowId: null,
    outputAssetId: null,
    previewAssetId: null,
    errorMessage: null,
    startedAt: new Date(),
    completedAt: null,
    createdAt: new Date(),
  };

  it("POST /api/renders starts a render job", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject as any);
    vi.mocked(db.query.assets.findMany).mockResolvedValueOnce([]);
    vi.mocked(db.query.renders.findFirst).mockResolvedValueOnce(undefined);
    vi.mocked(db.insert).mockReturnValueOnce({
      values: vi.fn().mockReturnValueOnce({
        returning: vi.fn().mockResolvedValueOnce([mockRender]),
      }),
    } as any);
    vi.mocked(db.update).mockReturnValueOnce({
      set: vi.fn().mockReturnValueOnce({
        where: vi.fn().mockReturnValueOnce({
          returning: vi.fn().mockResolvedValueOnce([mockRender]),
        }),
      }),
    } as any);
    vi.mocked(startRenderWorkflow).mockResolvedValueOnce("wf-123");

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/renders",
      payload: { projectId: PROJ_ID },
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.job.id).toBe(RENDER_ID);
    expect(vi.mocked(startRenderWorkflow)).toHaveBeenCalled();
    expect(vi.mocked(enqueueJob)).toHaveBeenCalled();
  });

  it("POST /api/renders returns 404 for missing project", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(undefined);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/renders",
      payload: { projectId: PROJ_ID },
    });
    expect(res.statusCode).toBe(404);
  });

  it("POST /api/renders returns 403 for other user's project", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce({
      ...mockProject,
      userId: "other-user-id",
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/renders",
      payload: { projectId: PROJ_ID },
    });
    expect(res.statusCode).toBe(403);
  });

  it("POST /api/renders returns 422 when missing assets", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce({
      ...mockProject,
      referenceAssetId: null,
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/renders",
      payload: { projectId: PROJ_ID },
    });
    expect(res.statusCode).toBe(422);
  });

  it("POST /api/renders returns 409 when render already in progress", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject as any);
    vi.mocked(db.query.renders.findFirst).mockResolvedValueOnce(mockRender as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/renders",
      payload: { projectId: PROJ_ID },
    });
    expect(res.statusCode).toBe(409);
  });

  it("GET /api/renders/:jobId returns render job", async () => {
    vi.mocked(db.query.renders.findFirst).mockResolvedValueOnce({ ...mockRender, project: mockProject } as any);

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: `/api/renders/${RENDER_ID}` });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.job.id).toBe(RENDER_ID);
  });

  it("GET /api/renders/project/:projectId lists renders", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject as any);
    vi.mocked(db.query.renders.findMany).mockResolvedValueOnce([mockRender] as any);

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: `/api/renders/project/${PROJ_ID}` });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.jobs).toHaveLength(1);
  });
});
