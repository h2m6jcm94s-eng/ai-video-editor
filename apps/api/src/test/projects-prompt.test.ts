import { beforeEach, describe, expect, it, vi } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";

describe("Project Prompt Route", () => {
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
    cutList: {
      globals: {
        totalDurationS: 30,
        tempoBpm: 120,
        timeSignature: "4/4",
        energyCurve: [],
        sectionMarkers: [],
        aspectRatio: "9:16",
      },
      slots: [
        {
          index: 0,
          startS: 0,
          durationS: 5,
          beatIndex: 0,
          section: "intro",
          transitionIn: "hard_cut",
          transitionOut: "hard_cut",
          targetShotType: "wide",
          subjectHint: "establishing",
          motionHint: "static",
          energyLevel: 0.5,
          requiredTags: [],
          avoidTags: [],
          effects: [],
        },
      ],
      overlays: [],
      audioTracks: [],
    },
    renderAssetId: null,
    createdAt: new Date(),
    updatedAt: new Date(),
  };

  it("POST /api/projects/:id/prompt edits cutlist", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject);
    vi.mocked(db.update).mockReturnValueOnce({
      set: vi.fn().mockReturnValueOnce({
        where: vi.fn().mockReturnValueOnce({
          returning: vi.fn().mockResolvedValueOnce([mockProject]),
        }),
      }),
    } as any);

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce({
        json: async () => ({
          content: [
            {
              type: "text",
              text: JSON.stringify({
                diff: [{ op: "replace", path: "/slots/0/durationS", value: 10 }],
                explanation: "Extended",
              }),
            },
          ],
        }),
        ok: true,
        status: 200,
      } as any),
    );
    vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
    vi.stubEnv("AI_PROVIDER", "claude");

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/projects/proj-1/prompt",
      payload: { prompt: "make the first clip longer" },
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.explanation).toBe("Extended");
    expect(body.diff).toHaveLength(1);
  });

  it("POST returns 404 for missing project", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(undefined);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/projects/proj-999/prompt",
      payload: { prompt: "test" },
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
      url: "/api/projects/proj-1/prompt",
      payload: { prompt: "test" },
    });
    expect(res.statusCode).toBe(403);
  });

  it("POST returns 400 when project has no cutlist", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce({
      ...mockProject,
      cutList: null,
    });

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/projects/proj-1/prompt",
      payload: { prompt: "test" },
    });
    expect(res.statusCode).toBe(400);
    expect(JSON.parse(res.body).code).toBe("NO_CUTLIST");
  });

  it("POST returns 503 when all AI providers fail", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValueOnce(new Error("Claude down")).mockRejectedValueOnce(new Error("OpenAI down")),
    );
    vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
    vi.stubEnv("OPENAI_API_KEY", "sk-openai-test");
    vi.stubEnv("AI_PROVIDER", "claude");

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/projects/proj-1/prompt",
      payload: { prompt: "test" },
    });
    expect(res.statusCode).toBe(503);
    const body = JSON.parse(res.body);
    expect(body.code).toBe("ALL_PROVIDERS_FAILED");
    expect(body.details).toBeDefined();
  });
});
