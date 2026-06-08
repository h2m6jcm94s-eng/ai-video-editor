import { describe, it, expect, vi, beforeEach } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";

describe("Project Transcribe Route", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockProject = {
    id: "proj-1",
    name: "Test Project",
    status: "uploading",
    userId: "test-user-id",
    styleTier: "full_style",
    mode: "auto",
    referenceAssetId: null,
    songAssetId: null,
    clipAssetIds: [],
    cutList: null,
    renderAssetId: null,
    createdAt: new Date(),
    updatedAt: new Date(),
  };

  const mockAsset = {
    id: "asset-1",
    projectId: "proj-1",
    type: "song",
    filename: "song.mp3",
    mimeType: "audio/mpeg",
    sizeBytes: 1024,
    durationSec: 120,
    width: null,
    height: null,
    fps: null,
    storageKey: "projects/proj-1/song.mp3",
    storageUrl: "https://r2.example.com/song.mp3",
    metadata: null,
    createdAt: new Date(),
  };

  it("POST /api/projects/:id/transcribe returns subtitles", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject);
    vi.mocked(db.query.assets.findFirst).mockResolvedValueOnce(mockAsset);

    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce({
      json: async () => ({
        segments: [
          { text: "Hello", start: 0, end: 1 },
          { text: "World", start: 1.5, end: 3 },
        ],
      }),
      ok: true,
      status: 200,
    } as any));
    vi.stubEnv("OPENAI_API_KEY", "sk-openai-test");

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/projects/proj-1/transcribe",
      payload: { assetId: "asset-1" },
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.subtitles).toHaveLength(2);
    expect(body.subtitles[0].text).toBe("Hello");
    expect(body.subtitles[0].startS).toBe(0);
  });

  it("POST returns 404 for missing project", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(undefined);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/projects/proj-999/transcribe",
      payload: { assetId: "asset-1" },
    });
    expect(res.statusCode).toBe(404);
  });

  it("POST returns 403 for other user's project", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce({
      ...mockProject,
      userId: "other-user-id",
    });

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/projects/proj-1/transcribe",
      payload: { assetId: "asset-1" },
    });
    expect(res.statusCode).toBe(403);
  });

  it("POST returns 400 when assetId is missing", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/projects/proj-1/transcribe",
      payload: {},
    });
    expect(res.statusCode).toBe(400);
    expect(JSON.parse(res.body).code).toBe("VALIDATION_ERROR");
  });

  it("POST returns 404 when asset not found", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject);
    vi.mocked(db.query.assets.findFirst).mockResolvedValueOnce(undefined);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/projects/proj-1/transcribe",
      payload: { assetId: "asset-999" },
    });
    expect(res.statusCode).toBe(404);
  });

  it("POST returns 500 when transcription fails", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject);
    vi.mocked(db.query.assets.findFirst).mockResolvedValueOnce(mockAsset);

    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 429,
      text: async () => "Rate limited",
    } as any));
    vi.stubEnv("OPENAI_API_KEY", "sk-openai-test");

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/projects/proj-1/transcribe",
      payload: { assetId: "asset-1" },
    });
    expect(res.statusCode).toBe(500);
    expect(JSON.parse(res.body).code).toBe("TRANSCRIBE_ERROR");
  });
});
