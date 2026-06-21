import { beforeEach, describe, expect, it, vi } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";
import { startSegmentSubjectWorkflow } from "../services/temporal";

describe("Segment Routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const PROJ_ID = "8562dc1a-1493-42ee-ab6e-1075b83c88d6";
  const ASSET_ID = "fc6b55b4-01cd-431b-808a-35b4f28613e1";

  const mockProject = {
    id: PROJ_ID,
    userId: "test-user-id",
    name: "Test",
    status: "uploading",
    referenceAssetId: ASSET_ID,
    songAssetId: null,
    clipAssetIds: [],
    styleTier: "full_style",
    mode: "auto",
  };

  const mockAsset = {
    id: ASSET_ID,
    projectId: PROJ_ID,
    type: "reference_video",
    storageKey: "uploads/ref.mp4",
    filename: "ref.mp4",
    mimeType: "video/mp4",
    sizeBytes: 1024,
    status: "complete",
    metadata: {},
    createdAt: new Date(),
    updatedAt: new Date(),
  };

  it("POST /api/segments starts a segmentation workflow", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject as any);
    vi.mocked(db.query.assets.findFirst).mockResolvedValueOnce(mockAsset as any);
    vi.mocked(startSegmentSubjectWorkflow).mockResolvedValueOnce("segment-wf-123");

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/segments",
      payload: {
        projectId: PROJ_ID,
        assetId: ASSET_ID,
        prompt: "the dancer",
        mode: "image",
        frameIndex: 0,
      },
    });

    expect(res.statusCode).toBe(202);
    const body = JSON.parse(res.body);
    expect(body.workflowId).toBe("segment-wf-123");
    expect(body.status).toBe("queued");
    expect(startSegmentSubjectWorkflow).toHaveBeenCalledWith(
      expect.objectContaining({ projectId: PROJ_ID, assetId: ASSET_ID, prompt: "the dancer" }),
    );
  });

  it("POST /api/segments returns 404 for missing project", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(undefined);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/segments",
      payload: { projectId: PROJ_ID, assetId: ASSET_ID, prompt: "the dancer" },
    });

    expect(res.statusCode).toBe(404);
    expect(JSON.parse(res.body).code).toBe("NOT_FOUND");
  });

  it("POST /api/segments returns 403 for other user's project", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce({
      ...mockProject,
      userId: "other-user-id",
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/segments",
      payload: { projectId: PROJ_ID, assetId: ASSET_ID, prompt: "the dancer" },
    });

    expect(res.statusCode).toBe(403);
    expect(JSON.parse(res.body).code).toBe("FORBIDDEN");
  });

  it("POST /api/segments returns 404 when asset does not belong to project", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject as any);
    vi.mocked(db.query.assets.findFirst).mockResolvedValueOnce({
      ...mockAsset,
      projectId: "other-project-id",
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/segments",
      payload: { projectId: PROJ_ID, assetId: ASSET_ID, prompt: "the dancer" },
    });

    expect(res.statusCode).toBe(404);
    expect(JSON.parse(res.body).code).toBe("NOT_FOUND");
  });

  it("POST /api/segments returns 422 when asset upload is incomplete", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject as any);
    vi.mocked(db.query.assets.findFirst).mockResolvedValueOnce({
      ...mockAsset,
      storageKey: null,
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/segments",
      payload: { projectId: PROJ_ID, assetId: ASSET_ID, prompt: "the dancer" },
    });

    expect(res.statusCode).toBe(422);
    expect(JSON.parse(res.body).code).toBe("UPLOAD_INCOMPLETE");
  });

  it("GET /api/segments/:workflowId returns query result", async () => {
    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/segments/segment-wf-123" });

    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.workflowId).toBe("segment-wf-123");
    expect(body.result).toEqual({ status: "completed" });
  });
});
