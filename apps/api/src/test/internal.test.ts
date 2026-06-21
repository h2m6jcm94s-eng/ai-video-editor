import { beforeEach, describe, expect, it, vi } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";
import { recordUserEvent } from "../lib/userEvents";

vi.mock("../lib/userEvents", () => ({
  recordUserEvent: vi.fn(),
}));

const TOKEN = process.env.INTERNAL_WORKER_TOKEN;

describe("Internal Routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("POST /api/internal/user-events returns 422 on invalid payload", async () => {
    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/internal/user-events",
      payload: { userId: "not-a-uuid", code: "", message: "" },
      headers: { "x-internal-token": process.env.INTERNAL_WORKER_TOKEN },
    });

    expect(res.statusCode).toBe(422);
    const body = JSON.parse(res.body);
    expect(body.code).toBe("VALIDATION_ERROR");
    // The invalid payload should not have been recorded as a user event.
    expect(recordUserEvent).not.toHaveBeenCalledWith(expect.objectContaining({ userId: "not-a-uuid" }));
  });

  it("POST /api/internal/user-events records a valid event", async () => {
    vi.mocked(recordUserEvent).mockResolvedValueOnce(undefined);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/internal/user-events",
      payload: {
        userId: "550e8400-e29b-41d4-a716-446655440000",
        code: "TEST_EVENT",
        message: "Something happened",
      },
      headers: { "x-internal-token": process.env.INTERNAL_WORKER_TOKEN },
    });

    expect(res.statusCode).toBe(200);
    expect(recordUserEvent).toHaveBeenCalled();
  });

  describe("Asset routes", () => {
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

    it("POST /api/internal/assets creates a mask asset", async () => {
      vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject as any);
      vi.mocked(db.insert).mockReturnValueOnce({
        values: vi.fn().mockReturnValueOnce({
          returning: vi.fn().mockResolvedValueOnce([mockAsset]),
        }),
      } as any);

      const app = await buildApp();
      const res = await app.inject({
        method: "POST",
        url: "/api/internal/assets",
        payload: {
          projectId: PROJ_ID,
          type: "mask",
          filename: "mask-0.png",
          mimeType: "image/png",
        },
        headers: { "x-internal-token": TOKEN },
      });

      expect(res.statusCode).toBe(200);
      const body = JSON.parse(res.body);
      expect(body.assetId).toBe(ASSET_ID);
      expect(body.asset.type).toBe("reference_video");
    });

    it("POST /api/internal/assets rejects without internal token", async () => {
      const app = await buildApp();
      const res = await app.inject({
        method: "POST",
        url: "/api/internal/assets",
        payload: {
          projectId: PROJ_ID,
          type: "mask",
          filename: "mask-0.png",
          mimeType: "image/png",
        },
      });

      expect(res.statusCode).toBe(401);
    });

    it("POST /api/internal/assets returns 404 for missing project", async () => {
      vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(undefined);

      const app = await buildApp();
      const res = await app.inject({
        method: "POST",
        url: "/api/internal/assets",
        payload: {
          projectId: PROJ_ID,
          type: "mask",
          filename: "mask-0.png",
          mimeType: "image/png",
        },
        headers: { "x-internal-token": TOKEN },
      });

      expect(res.statusCode).toBe(404);
    });

    it("PATCH /api/internal/assets/:assetId/metadata merges metadata", async () => {
      vi.mocked(db.query.assets.findFirst).mockResolvedValueOnce(mockAsset as any);
      vi.mocked(db.update).mockReturnValueOnce({
        set: vi.fn().mockReturnValueOnce({
          where: vi.fn().mockReturnValueOnce({
            returning: vi
              .fn()
              .mockResolvedValueOnce([{ ...mockAsset, metadata: { segmentation: { maskCount: 1 } } }]),
          }),
        }),
      } as any);

      const app = await buildApp();
      const res = await app.inject({
        method: "PATCH",
        url: `/api/internal/assets/${ASSET_ID}/metadata`,
        payload: { metadata: { segmentation: { maskCount: 1 } } },
        headers: { "x-internal-token": TOKEN },
      });

      expect(res.statusCode).toBe(200);
      const body = JSON.parse(res.body);
      expect(body.asset.metadata.segmentation.maskCount).toBe(1);
    });

    it("PATCH /api/internal/assets/:assetId/metadata returns 404 for missing asset", async () => {
      vi.mocked(db.query.assets.findFirst).mockResolvedValueOnce(undefined);

      const app = await buildApp();
      const res = await app.inject({
        method: "PATCH",
        url: `/api/internal/assets/${ASSET_ID}/metadata`,
        payload: { metadata: { foo: "bar" } },
        headers: { "x-internal-token": TOKEN },
      });

      expect(res.statusCode).toBe(404);
    });

    it("PATCH /api/internal/assets/:assetId/metadata rejects invalid payload", async () => {
      const app = await buildApp();
      const res = await app.inject({
        method: "PATCH",
        url: `/api/internal/assets/${ASSET_ID}/metadata`,
        payload: { extra: "not allowed" },
        headers: { "x-internal-token": TOKEN },
      });

      expect(res.statusCode).toBe(422);
      expect(JSON.parse(res.body).code).toBe("VALIDATION_ERROR");
    });

    it("PATCH /api/internal/assets/:assetId/metadata rejects oversized metadata", async () => {
      const app = await buildApp();
      const huge = { metadata: { blob: "x".repeat(65537) } };
      const res = await app.inject({
        method: "PATCH",
        url: `/api/internal/assets/${ASSET_ID}/metadata`,
        payload: huge,
        headers: { "x-internal-token": TOKEN },
      });

      expect(res.statusCode).toBe(422);
      expect(JSON.parse(res.body).code).toBe("VALIDATION_ERROR");
    });
  });
});
