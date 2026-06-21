import { beforeEach, describe, expect, it, vi } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";
import { enqueueJob } from "../services/queue";
import { getStyleAnalysisFromWorkflow, startGenerateCutlistWorkflow } from "../services/temporal";

describe("Project generation routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const PROJ_ID = "8562dc1a-1493-42ee-ab6e-1075b83c88d6";
  const JOB_ID = "fc6b55b4-01cd-431b-808a-35b4f28613e1";

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
    styleAnalysis: null,
  };

  const mockJob = {
    id: JOB_ID,
    projectId: PROJ_ID,
    status: "queued",
    stage: "queued",
    progress: 0,
    workflowId: null,
    outputCutList: null,
    errorMessage: null,
    options: null,
    startedAt: new Date(),
    completedAt: null,
    createdAt: new Date(),
  };

  function mockAtomicStart(project = mockProject) {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(project as any);
    vi.mocked(db.query.generationJobs.findFirst).mockResolvedValueOnce(undefined);
    vi.mocked(db.insert).mockReturnValueOnce({
      values: vi.fn().mockReturnValueOnce({
        returning: vi.fn().mockResolvedValueOnce([mockJob]),
      }),
    } as any);
    vi.mocked(db.update).mockReturnValueOnce({
      set: vi.fn().mockReturnValueOnce({
        where: vi.fn().mockReturnValueOnce({
          returning: vi.fn().mockResolvedValueOnce([{ ...mockJob, workflowId: "generate-wf-123" }]),
        }),
      }),
    } as any);
    vi.mocked(db.query.assets.findMany).mockResolvedValueOnce([]);
  }

  it("POST /api/projects/:id/generate queues a generation job", async () => {
    mockAtomicStart();
    vi.mocked(getStyleAnalysisFromWorkflow).mockResolvedValueOnce({ color_palette: ["#000000"] });
    vi.mocked(startGenerateCutlistWorkflow).mockResolvedValueOnce("generate-wf-123");

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: `/api/projects/${PROJ_ID}/generate`,
      payload: {},
    });

    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.job.id).toBe(JOB_ID);
    expect(startGenerateCutlistWorkflow).toHaveBeenCalled();
    expect(enqueueJob).toHaveBeenCalledWith(expect.objectContaining({ type: "cutlist_generation" }));
  });

  it("POST /api/projects/:id/generate returns 409 when a generation is already running", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject as any);
    vi.mocked(db.query.generationJobs.findFirst).mockResolvedValueOnce(mockJob as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: `/api/projects/${PROJ_ID}/generate`,
      payload: {},
    });

    expect(res.statusCode).toBe(409);
    expect(JSON.parse(res.body).code).toBe("GENERATION_ALREADY_RUNNING");
  });

  it("POST /api/projects/:id/generate returns 422 when project is missing reference video", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce({
      ...mockProject,
      referenceAssetId: null,
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: `/api/projects/${PROJ_ID}/generate`,
      payload: {},
    });

    expect(res.statusCode).toBe(422);
    expect(JSON.parse(res.body).code).toBe("MISSING_ASSETS");
  });

  it("POST /api/projects/:id/generate returns 202 when style analysis is pending", async () => {
    mockAtomicStart();
    vi.mocked(getStyleAnalysisFromWorkflow).mockResolvedValueOnce(null);
    vi.mocked(db.delete).mockReturnValueOnce({
      where: vi.fn().mockResolvedValueOnce(undefined),
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: `/api/projects/${PROJ_ID}/generate`,
      payload: {},
    });

    expect(res.statusCode).toBe(202);
    expect(JSON.parse(res.body).code).toBe("PENDING");
  });

  it("GET /api/projects/:id/generation returns the latest generation job", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject as any);
    vi.mocked(db.query.generationJobs.findFirst).mockResolvedValueOnce(mockJob as any);

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: `/api/projects/${PROJ_ID}/generation` });

    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).job.id).toBe(JOB_ID);
  });

  it("GET /api/projects/:id/generation returns 404 when no generation job exists", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject as any);
    vi.mocked(db.query.generationJobs.findFirst).mockResolvedValueOnce(undefined);

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: `/api/projects/${PROJ_ID}/generation` });

    expect(res.statusCode).toBe(404);
  });
});
