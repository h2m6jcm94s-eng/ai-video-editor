import { beforeEach, describe, expect, it, vi } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";

describe("Command Routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockProject = {
    id: "proj-1",
    name: "Test Project",
    status: "uploading",
    userId: "test-user-id",
    styleTier: "full_remix",
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

  function mockUpdateReturning(project: any) {
    vi.mocked(db.update).mockReturnValue({
      set: vi.fn().mockReturnValue({
        where: vi.fn().mockReturnValue({
          returning: vi.fn().mockResolvedValue([project]),
        }),
      }),
    } as any);
  }

  it("POST /api/projects/:id/commands uses deterministic verb", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject);
    vi.mocked(db.query.assets.findMany).mockResolvedValueOnce([]);
    mockUpdateReturning(mockProject);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/projects/proj-1/commands",
      payload: { prompt: "trim slot 0 to 3 seconds" },
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.verb).toBe("trim_slot");
    expect(body.fallbackToLLM).toBe(false);
    expect(body.explanation).toContain("Trimmed");
    expect(body.diff).toHaveLength(1);
  });

  it("POST /api/projects/:id/commands falls back to LLM", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject);
    vi.mocked(db.query.assets.findMany).mockResolvedValueOnce([]);
    mockUpdateReturning(mockProject);

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce({
        json: async () => ({
          content: [
            {
              type: "text",
              text: JSON.stringify({
                diff: [{ op: "replace", path: "/slots/0/durationS", value: 10 }],
                explanation: "Extended via LLM",
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
      url: "/api/projects/proj-1/commands",
      payload: { prompt: "make it feel more cinematic" },
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.fallbackToLLM).toBe(true);
    expect(body.explanation).toBe("Extended via LLM");
  });

  it("POST /api/commands/parse returns parse result", async () => {
    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/commands/parse",
      payload: { prompt: "zoom in on the first clip" },
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.command.verb).toBe("zoom_in");
    expect(body.fallbackToLLM).toBe(false);
  });

  it("POST /api/projects/:id/commands returns 404 for missing project", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(undefined);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/projects/proj-999/commands",
      payload: { prompt: "trim slot 0" },
    });
    expect(res.statusCode).toBe(404);
  });

  it("POST /api/projects/:id/commands returns 403 for other user's project", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce({
      ...mockProject,
      userId: "other-user-id",
    });

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/projects/proj-1/commands",
      payload: { prompt: "trim slot 0" },
    });
    expect(res.statusCode).toBe(403);
  });
});
