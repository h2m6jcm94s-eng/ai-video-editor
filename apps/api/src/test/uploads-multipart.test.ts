import { beforeEach, describe, expect, it, vi } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";
import {
  abortMultipartUpload,
  completeMultipartUpload,
  createMultipartUpload,
  presignUploadPart,
} from "../services/storage";

describe("Multipart Upload Routes", () => {
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

  it("POST /api/uploads/multipart/init returns uploadId and asset", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject as any);
    vi.mocked(createMultipartUpload).mockResolvedValueOnce("upload-id-123");
    vi.mocked(db.insert).mockReturnValueOnce({
      values: vi.fn().mockReturnValueOnce({
        returning: vi.fn().mockResolvedValueOnce([mockAsset]),
      }),
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/uploads/multipart/init",
      payload: {
        projectId: PROJ_ID,
        filename: "big.mp4",
        mimeType: "video/mp4",
        type: "clip",
      },
    });

    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.uploadId).toBe("upload-id-123");
    expect(body.assetId).toBeDefined();
    expect(body.key).toBeDefined();
  });

  it("POST /api/uploads/multipart/init rejects invalid payload", async () => {
    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/uploads/multipart/init",
      payload: {
        projectId: "not-a-uuid",
        filename: "",
        mimeType: "video/mp4",
        type: "clip",
      },
    });
    expect(res.statusCode).toBe(422);
    expect(JSON.parse(res.body).code).toBe("VALIDATION_ERROR");
  });

  it("POST /api/uploads/multipart/sign-part returns presigned URL", async () => {
    vi.mocked(db.query.assets.findFirst).mockResolvedValueOnce({
      ...mockAsset,
      project: mockProject,
    } as any);
    vi.mocked(presignUploadPart).mockResolvedValueOnce("https://r2.example.com/part-1");

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/uploads/multipart/sign-part",
      payload: {
        uploadId: "upload-id-123",
        key: mockAsset.storageKey,
        partNumber: 1,
      },
    });

    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.url).toBe("https://r2.example.com/part-1");
  });

  it("POST /api/uploads/multipart/sign-part returns 404 for non-existent key", async () => {
    vi.mocked(db.query.assets.findFirst).mockResolvedValueOnce(undefined);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/uploads/multipart/sign-part",
      payload: {
        uploadId: "upload-id-123",
        key: "projects/other/key",
        partNumber: 1,
      },
    });

    expect(res.statusCode).toBe(404);
    expect(JSON.parse(res.body).code).toBe("NOT_FOUND");
  });

  it("POST /api/uploads/multipart/sign-part returns 403 for another user's asset", async () => {
    vi.mocked(db.query.assets.findFirst).mockResolvedValueOnce({
      ...mockAsset,
      project: { ...mockProject, userId: "other-user-id" },
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/uploads/multipart/sign-part",
      payload: {
        uploadId: "upload-id-123",
        key: mockAsset.storageKey,
        partNumber: 1,
      },
    });

    expect(res.statusCode).toBe(403);
    expect(JSON.parse(res.body).code).toBe("FORBIDDEN");
  });

  it("POST /api/uploads/multipart/complete updates asset and triggers probe", async () => {
    vi.mocked(db.query.assets.findFirst).mockResolvedValueOnce({
      ...mockAsset,
      project: mockProject,
    } as any);
    vi.mocked(completeMultipartUpload).mockResolvedValueOnce({});
    vi.mocked(db.update).mockReturnValueOnce({
      set: vi.fn().mockReturnValueOnce({
        where: vi.fn().mockReturnValueOnce({
          returning: vi.fn().mockResolvedValueOnce([{ ...mockAsset, sizeBytes: 200 * 1024 * 1024 }]),
        }),
      }),
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/uploads/multipart/complete",
      payload: {
        uploadId: "upload-id-123",
        key: mockAsset.storageKey,
        parts: [{ PartNumber: 1, ETag: '"etag1"' }],
        sizeBytes: 200 * 1024 * 1024,
      },
    });

    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.asset.sizeBytes).toBe(200 * 1024 * 1024);
    expect(completeMultipartUpload).toHaveBeenCalledWith(mockAsset.storageKey, "upload-id-123", [
      { PartNumber: 1, ETag: '"etag1"' },
    ]);
  });

  it("DELETE /api/uploads/multipart/abort calls abortMultipartUpload", async () => {
    vi.mocked(abortMultipartUpload).mockResolvedValueOnce({});

    const app = await buildApp();
    const res = await app.inject({
      method: "DELETE",
      url: "/api/uploads/multipart/abort",
      payload: {
        uploadId: "upload-id-123",
        key: "projects/test/key",
      },
    });

    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.ok).toBe(true);
    expect(abortMultipartUpload).toHaveBeenCalledWith("projects/test/key", "upload-id-123");
  });

  it("POST /api/uploads/:assetId/complete skips etag check for multipart uploads", async () => {
    const { headObject } = await import("../services/storage");
    vi.mocked(headObject).mockResolvedValueOnce({
      ETag: '"abc123"',
      ContentLength: 1024,
      PartsCount: 2,
    } as any);
    vi.mocked(db.query.assets.findFirst).mockResolvedValueOnce({
      ...mockAsset,
      metadata: { isMultipart: true },
      project: mockProject,
    } as any);
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
      payload: { sizeBytes: 1024, etag: "multipart-etag-digest" },
    });

    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.asset.sizeBytes).toBe(1024);
  });
});
