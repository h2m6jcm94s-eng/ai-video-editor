import { describe, it, expect, vi, beforeEach } from "vitest";
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
      globals: { total_duration_s: 30 },
      slots: [{ index: 0, start_s: 0, duration_s: 5 }],
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

    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce({
      json: async () => ({
        content: [{ type: "text", text: JSON.stringify({ diff: [{ op: "replace", path: "/slots/0/duration_s", value: 10 }], explanation: "Extended" }) }],
      }),
      ok: true,
      status: 200,
    } as any));
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

  it("POST returns 500 when AI service fails", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject);
    vi.stubGlobal("fetch", vi.fn()
      .mockRejectedValueOnce(new Error("Claude down"))
      .mockRejectedValueOnce(new Error("OpenAI down")));
    vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
    vi.stubEnv("OPENAI_API_KEY", "sk-openai-test");
    vi.stubEnv("AI_PROVIDER", "claude");

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/projects/proj-1/prompt",
      payload: { prompt: "test" },
    });
    expect(res.statusCode).toBe(500);
    expect(JSON.parse(res.body).code).toBe("INTERNAL_ERROR");
  });

});
