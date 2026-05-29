import { describe, it, expect, vi, beforeEach } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";
import { createPresignedUploadUrl } from "../services/storage";

describe("Upload Routes", () => {
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
  };

  const mockAsset = {
    id: ASSET_ID,
    projectId: PROJ_ID,
    type: "clip",
    filename: "test.mp4",
    mimeType: "video/mp4",
    sizeBytes: 0,
    storageKey: `projects/${PROJ_ID}/clip/${ASSET_ID}-test.mp4`,
    storageUrl: "",
    metadata: {},
  };

  it("POST /api/uploads/presigned returns upload URL", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject as any);
    vi.mocked(createPresignedUploadUrl).mockResolvedValueOnce({
      url: "https://r2.example.com/upload",
      fields: {},
    });
    vi.mocked(db.insert).mockReturnValueOnce({
      values: vi.fn().mockReturnValueOnce({
        returning: vi.fn().mockResolvedValueOnce([mockAsset]),
      }),
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/uploads/presigned",
      payload: {
        projectId: PROJ_ID,
        filename: "test.mp4",
        mimeType: "video/mp4",
        type: "clip",
      },
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.url).toBe("https://r2.example.com/upload");
    expect(body.assetId).toBeDefined();
  });

  it("POST /api/uploads/presigned rejects invalid MIME type", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/uploads/presigned",
      payload: {
        projectId: PROJ_ID,
        filename: "test.exe",
        mimeType: "application/x-msdownload",
        type: "clip",
      },
    });
    expect(res.statusCode).toBe(422);
  });

  it("POST /api/uploads/presigned returns 403 for other user's project", async () => {
    const mockFn = vi.fn().mockResolvedValueOnce({
      ...mockProject,
      userId: "other-user-id",
    } as any);
    db.query.projects.findFirst = mockFn;

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/uploads/presigned",
      payload: {
        projectId: PROJ_ID,
        filename: "test.mp4",
        mimeType: "video/mp4",
        type: "clip",
      },
    });
    expect(res.statusCode).toBe(403);
  });

  it("POST /api/uploads/:assetId/complete updates asset", async () => {
    vi.mocked(db.query.assets.findFirst).mockResolvedValueOnce(mockAsset as any);
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject as any);
    vi.mocked(db.update).mockReturnValueOnce({
      set: vi.fn().mockReturnValueOnce({
        where: vi.fn().mockReturnValueOnce({
          returning: vi.fn().mockResolvedValueOnce([{ ...mockAsset, sizeBytes: 1024 }]),
        }),
      }),
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: `/api/uploads/${ASSET_ID}/complete`,
      payload: { sizeBytes: 1024, etag: '"abc123"' },
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.asset.sizeBytes).toBe(1024);
  });

  it("POST /api/uploads/:assetId/complete rejects negative size", async () => {
    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: `/api/uploads/${ASSET_ID}/complete`,
      payload: { sizeBytes: -1, etag: '"abc123"' },
    });
    expect(res.statusCode).toBe(422);
  });

  it("GET /api/uploads/:assetId returns asset", async () => {
    vi.mocked(db.query.assets.findFirst).mockResolvedValueOnce(mockAsset as any);
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject as any);

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: `/api/uploads/${ASSET_ID}` });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.asset.id).toBe(ASSET_ID);
  });
});
