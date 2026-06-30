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
      styleTier: "full_remix",
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

  describe("Generated cutlist routes", () => {
    const PROJ_ID = "8562dc1a-1493-42ee-ab6e-1075b83c88d6";
    const JOB_ID = "fc6b55b4-01cd-431b-808a-35b4f28613e1";

    const mockProject = {
      id: PROJ_ID,
      userId: "test-user-id",
      name: "Test",
      status: "uploading",
      referenceAssetId: null,
      songAssetId: null,
      clipAssetIds: [],
      styleTier: "full_remix",
      mode: "auto",
      cutList: null,
      createdAt: new Date(),
      updatedAt: new Date(),
    };

    const mockJob = {
      id: JOB_ID,
      projectId: PROJ_ID,
      status: "running",
      stage: "generating_cutlist",
      progress: 75,
      workflowId: "generate-wf-1",
      outputCutList: null,
      errorMessage: null,
      options: null,
      startedAt: new Date(),
      completedAt: null,
      createdAt: new Date(),
    };

    const validCutList = {
      globals: {
        totalDurationS: 60,
        tempoBpm: 128,
        timeSignature: "4/4",
        aspectRatio: "9:16",
      },
      slots: [
        {
          index: 0,
          startS: 0,
          durationS: 2,
          beatIndex: 0,
          section: "intro",
          targetShotType: "wide",
          subjectHint: "person",
          motionHint: "static",
        },
      ],
    };

    it("PATCH /api/internal/projects/:id/generated-cutlist persists cutlist and completes job", async () => {
      vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject as any);
      vi.mocked(db.query.generationJobs.findFirst).mockResolvedValueOnce(mockJob as any);
      vi.mocked(db.update).mockReturnValueOnce({
        set: vi.fn().mockReturnValueOnce({
          where: vi.fn().mockReturnValueOnce({
            returning: vi.fn().mockResolvedValueOnce([{ ...mockProject, cutList: validCutList }]),
          }),
        }),
      } as any);
      vi.mocked(db.update).mockReturnValueOnce({
        set: vi.fn().mockReturnValueOnce({
          where: vi.fn().mockReturnValueOnce({
            returning: vi.fn().mockResolvedValueOnce([{ ...mockJob, status: "complete", progress: 100 }]),
          }),
        }),
      } as any);

      const app = await buildApp();
      const res = await app.inject({
        method: "PATCH",
        url: `/api/internal/projects/${PROJ_ID}/generated-cutlist`,
        payload: { cutList: validCutList, generationJobId: JOB_ID },
        headers: { "x-internal-token": TOKEN },
      });

      expect(res.statusCode).toBe(200);
      const body = JSON.parse(res.body);
      expect(body.job.status).toBe("complete");
      expect(body.project.cutList).toEqual(validCutList);
    });

    it("PATCH /api/internal/projects/:id/generated-cutlist returns 404 for missing job", async () => {
      vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject as any);
      vi.mocked(db.query.generationJobs.findFirst).mockResolvedValueOnce(undefined);

      const app = await buildApp();
      const res = await app.inject({
        method: "PATCH",
        url: `/api/internal/projects/${PROJ_ID}/generated-cutlist`,
        payload: { cutList: validCutList, generationJobId: JOB_ID },
        headers: { "x-internal-token": TOKEN },
      });

      expect(res.statusCode).toBe(404);
    });

    it("POST /api/internal/generation-jobs/:jobId/fail marks a job as failed", async () => {
      vi.mocked(db.query.generationJobs.findFirst).mockResolvedValueOnce(mockJob as any);
      vi.mocked(db.update).mockReturnValueOnce({
        set: vi.fn().mockReturnValueOnce({
          where: vi.fn().mockReturnValueOnce({
            returning: vi
              .fn()
              .mockResolvedValueOnce([{ ...mockJob, status: "failed", errorMessage: "boom" }]),
          }),
        }),
      } as any);

      const app = await buildApp();
      const res = await app.inject({
        method: "POST",
        url: `/api/internal/generation-jobs/${JOB_ID}/fail`,
        payload: { errorMessage: "boom" },
        headers: { "x-internal-token": TOKEN },
      });

      expect(res.statusCode).toBe(200);
      expect(JSON.parse(res.body).job.status).toBe("failed");
    });

    it("POST /api/internal/generation-jobs/:jobId/fail rejects missing error message", async () => {
      const app = await buildApp();
      const res = await app.inject({
        method: "POST",
        url: `/api/internal/generation-jobs/${JOB_ID}/fail`,
        payload: {},
        headers: { "x-internal-token": TOKEN },
      });

      expect(res.statusCode).toBe(422);
    });
  });

  describe("Render outcome routes", () => {
    const RENDER_ID = "fc6b55b4-01cd-431b-808a-35b4f28613e1";
    const PROJ_ID = "8562dc1a-1493-42ee-ab6e-1075b83c88d6";

    const mockRender = {
      id: RENDER_ID,
      projectId: PROJ_ID,
      userId: "test-user-id",
      status: "complete",
    };

    it("POST /api/renders/:jobId/outcomes records an implicit worker event", async () => {
      vi.mocked(db.query.renders.findFirst).mockResolvedValueOnce(mockRender as any);
      vi.mocked(db.insert).mockReturnValueOnce({
        values: vi.fn().mockReturnValueOnce({
          onConflictDoUpdate: vi.fn().mockResolvedValueOnce(undefined),
        }),
      } as any);

      const app = await buildApp();
      const res = await app.inject({
        method: "POST",
        url: `/api/renders/${RENDER_ID}/outcomes`,
        payload: { exported: true, inferredQualityScore: 0.85 },
        headers: { "x-internal-token": TOKEN },
      });

      expect(res.statusCode).toBe(200);
      expect(JSON.parse(res.body).ok).toBe(true);
    });

    it("POST /api/renders/:jobId/outcomes rejects without internal token", async () => {
      const app = await buildApp();
      const res = await app.inject({
        method: "POST",
        url: `/api/renders/${RENDER_ID}/outcomes`,
        payload: { exported: true },
      });

      expect(res.statusCode).toBe(401);
    });
  });

  describe("Behavior corpus routes", () => {
    it("GET /api/internal/behavior-corpus lists public + user entries", async () => {
      vi.mocked(db.query.behaviorCorpusEntries.findMany).mockResolvedValueOnce([
        { id: "entry-1", qualityWeight: 0.9 },
      ] as any);

      const app = await buildApp();
      const res = await app.inject({
        method: "GET",
        url: "/api/internal/behavior-corpus?userId=550e8400-e29b-41d4-a716-446655440000",
        headers: { "x-internal-token": TOKEN },
      });

      expect(res.statusCode).toBe(200);
      expect(JSON.parse(res.body).entries).toHaveLength(1);
    });

    it("POST /api/internal/behavior-corpus creates an entry", async () => {
      vi.mocked(db.query.behaviorCorpusEntries.findMany).mockResolvedValueOnce([]);
      vi.mocked(db.insert).mockReturnValueOnce({
        values: vi.fn().mockReturnValueOnce({
          returning: vi.fn().mockResolvedValueOnce([{ id: "entry-1", status: "active" }]),
        }),
      } as any);

      const app = await buildApp();
      const res = await app.inject({
        method: "POST",
        url: "/api/internal/behavior-corpus",
        payload: {
          signals: { clip_count: 3 },
          behavior: { cut_density_per_sec: 0.2 },
          qualityWeight: 0.8,
          userId: "550e8400-e29b-41d4-a716-446655440000",
        },
        headers: { "x-internal-token": TOKEN },
      });

      expect(res.statusCode).toBe(200);
      const body = JSON.parse(res.body);
      expect(body.entry.id).toBe("entry-1");
      expect(body.entry.status).toBe("active");
    });

    it("POST /api/internal/behavior-corpus rejects entries over weekly cap", async () => {
      vi.mocked(db.select).mockReturnValueOnce({
        from: vi.fn().mockReturnValueOnce({
          where: vi.fn().mockResolvedValueOnce([{ value: 10 }]),
        }),
      } as any);

      const app = await buildApp();
      const res = await app.inject({
        method: "POST",
        url: "/api/internal/behavior-corpus",
        payload: {
          signals: { clip_count: 3 },
          behavior: { cut_density_per_sec: 0.2 },
          qualityWeight: 0.8,
          userId: "550e8400-e29b-41d4-a716-446655440000",
        },
        headers: { "x-internal-token": TOKEN },
      });

      expect(res.statusCode).toBe(429);
      expect(JSON.parse(res.body).code).toBe("CORPUS_CAP_EXCEEDED");
    });

    it("POST /api/internal/behavior-corpus quarantines anomalous entries", async () => {
      vi.mocked(db.query.behaviorCorpusEntries.findMany).mockResolvedValueOnce(
        Array.from({ length: 20 }, (_, i) => ({
          signals: { clip_count: 5 + i * 0.1 },
        })) as any,
      );
      vi.mocked(db.insert).mockReturnValueOnce({
        values: vi.fn().mockReturnValueOnce({
          returning: vi.fn().mockResolvedValueOnce([{ id: "entry-q", status: "quarantined" }]),
        }),
      } as any);

      const app = await buildApp();
      const res = await app.inject({
        method: "POST",
        url: "/api/internal/behavior-corpus",
        payload: {
          signals: { clip_count: 500 },
          behavior: { cut_density_per_sec: 0.2 },
          qualityWeight: 0.8,
          userId: "550e8400-e29b-41d4-a716-446655440000",
        },
        headers: { "x-internal-token": TOKEN },
      });

      expect(res.statusCode).toBe(200);
      const body = JSON.parse(res.body);
      expect(body.entry.id).toBe("entry-q");
      expect(body.entry.status).toBe("quarantined");
    });
  });

  describe("Corpus ingestion route", () => {
    const RENDER_ID = "fc6b55b4-01cd-431b-808a-35b4f28613e1";
    const PROJ_ID = "8562dc1a-1493-42ee-ab6e-1075b83c88d6";
    const USER_ID = "550e8400-e29b-41d4-a716-446655440000";
    const MS_PER_DAY = 24 * 60 * 60 * 1000;

    const mockRender = (completedAt: Date) => ({
      id: RENDER_ID,
      projectId: PROJ_ID,
      userId: USER_ID,
      status: "complete",
      completedAt,
    });

    const mockSignals = { id: "signals-1", renderId: RENDER_ID, signals: { clip_count: 3 } };
    const mockBehavior = { id: "behavior-1", renderId: RENDER_ID, cut_density_per_sec: 0.2 };
    const mockProfile = { id: "profile-1", userId: USER_ID, contributeToGlobalCorpus: true };

    it("POST /api/internal/renders/:renderId/ingest-to-corpus finalizes and ingests after 7 days", async () => {
      vi.mocked(db.query.renders.findFirst).mockResolvedValueOnce(
        mockRender(new Date(Date.now() - 8 * MS_PER_DAY)) as any,
      );
      vi.mocked(db.query.renderSignals.findFirst).mockResolvedValueOnce(mockSignals as any);
      vi.mocked(db.query.renderBehavior.findFirst).mockResolvedValueOnce(mockBehavior as any);
      vi.mocked(db.query.renderOutcomes.findFirst).mockResolvedValueOnce(undefined);
      vi.mocked(db.query.userTasteProfiles.findFirst).mockResolvedValueOnce(mockProfile as any);
      vi.mocked(db.query.behaviorCorpusEntries.findMany).mockResolvedValueOnce([]);

      // First insert finalizes the outcome; second insert creates the corpus entry.
      vi.mocked(db.insert)
        .mockReturnValueOnce({
          values: vi.fn().mockReturnValueOnce({
            onConflictDoUpdate: vi.fn().mockResolvedValueOnce(undefined),
          }),
        } as any)
        .mockReturnValueOnce({
          values: vi.fn().mockReturnValueOnce({
            returning: vi.fn().mockResolvedValueOnce([{ id: "entry-1", status: "active" }]),
          }),
        } as any);

      const app = await buildApp();
      const res = await app.inject({
        method: "POST",
        url: `/api/internal/renders/${RENDER_ID}/ingest-to-corpus`,
        payload: { qualityWeight: 0.8 },
        headers: { "x-internal-token": TOKEN },
      });

      expect(res.statusCode).toBe(200);
      expect(JSON.parse(res.body).entry.id).toBe("entry-1");
    });

    it("POST /api/internal/renders/:renderId/ingest-to-corpus rejects before the 7-day window closes", async () => {
      vi.mocked(db.query.renders.findFirst).mockResolvedValueOnce(
        mockRender(new Date(Date.now() - MS_PER_DAY)) as any,
      );
      vi.mocked(db.query.renderSignals.findFirst).mockResolvedValueOnce(mockSignals as any);
      vi.mocked(db.query.renderBehavior.findFirst).mockResolvedValueOnce(mockBehavior as any);
      vi.mocked(db.query.renderOutcomes.findFirst).mockResolvedValueOnce({ isFinalized: false } as any);

      const app = await buildApp();
      const res = await app.inject({
        method: "POST",
        url: `/api/internal/renders/${RENDER_ID}/ingest-to-corpus`,
        payload: { qualityWeight: 0.8 },
        headers: { "x-internal-token": TOKEN },
      });

      expect(res.statusCode).toBe(425);
      expect(JSON.parse(res.body).code).toBe("OUTCOME_WINDOW_OPEN");
    });

    it("POST /api/internal/renders/:renderId/ingest-to-corpus skips excluded projects", async () => {
      vi.mocked(db.query.renders.findFirst).mockResolvedValueOnce(
        mockRender(new Date(Date.now() - 8 * MS_PER_DAY)) as any,
      );
      vi.mocked(db.query.renderSignals.findFirst).mockResolvedValueOnce(mockSignals as any);
      vi.mocked(db.query.renderBehavior.findFirst).mockResolvedValueOnce(mockBehavior as any);
      vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce({ excludeFromLearning: true } as any);

      const app = await buildApp();
      const res = await app.inject({
        method: "POST",
        url: `/api/internal/renders/${RENDER_ID}/ingest-to-corpus`,
        payload: { qualityWeight: 0.8 },
        headers: { "x-internal-token": TOKEN },
      });

      expect(res.statusCode).toBe(200);
      const body = JSON.parse(res.body);
      expect(body.excluded).toBe(true);
      expect(body.ok).toBe(true);
    });
  });

  describe("User taste profile routes", () => {
    const USER_ID = "550e8400-e29b-41d4-a716-446655440000";

    it("GET /api/internal/user-taste-profiles/:userId creates a default profile if missing", async () => {
      vi.mocked(db.query.userTasteProfiles.findFirst).mockResolvedValueOnce(undefined);
      vi.mocked(db.insert).mockReturnValueOnce({
        values: vi.fn().mockReturnValueOnce({
          returning: vi.fn().mockResolvedValueOnce([{ id: "profile-1", userId: USER_ID }]),
        }),
      } as any);

      const app = await buildApp();
      const res = await app.inject({
        method: "GET",
        url: `/api/internal/user-taste-profiles/${USER_ID}`,
        headers: { "x-internal-token": TOKEN },
      });

      expect(res.statusCode).toBe(200);
      expect(JSON.parse(res.body).profile.userId).toBe(USER_ID);
    });

    it("PUT /api/internal/user-taste-profiles/:userId/bias merges bias deltas", async () => {
      vi.mocked(db.query.userTasteProfiles.findFirst).mockResolvedValueOnce({
        id: "profile-1",
        userId: USER_ID,
        clusterBiasVectors: { general: { cut_density_per_sec: 0.1 } },
        profileConfidence: 0.1,
      } as any);
      vi.mocked(db.update).mockReturnValueOnce({
        set: vi.fn().mockReturnValueOnce({
          where: vi.fn().mockReturnValueOnce({
            returning: vi.fn().mockResolvedValueOnce([{ id: "profile-1" }]),
          }),
        }),
      } as any);

      const app = await buildApp();
      const res = await app.inject({
        method: "PUT",
        url: `/api/internal/user-taste-profiles/${USER_ID}/bias`,
        payload: {
          cluster: "general",
          biasVector: { cut_density_per_sec: 0.05 },
          profileConfidenceDelta: 0.1,
        },
        headers: { "x-internal-token": TOKEN },
      });

      expect(res.statusCode).toBe(200);
    });
  });
});
