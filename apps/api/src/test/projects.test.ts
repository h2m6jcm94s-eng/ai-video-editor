import { beforeEach, describe, expect, it, vi } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";
import * as cache from "../lib/cache";
import { getStyleAnalysisFromWorkflow } from "../services/temporal";

describe("Project Routes", () => {
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
    cutList: null,
    renderAssetId: null,
    createdAt: new Date(),
    updatedAt: new Date(),
  };

  it("GET /api/projects lists user projects", async () => {
    vi.mocked(db.query.projects.findMany).mockResolvedValueOnce([mockProject]);

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/projects" });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.projects).toHaveLength(1);
    expect(body.projects[0].name).toBe("Test Project");
  });

  it("POST /api/projects creates a project", async () => {
    vi.mocked(db.insert).mockReturnValueOnce({
      values: vi.fn().mockReturnValueOnce({
        returning: vi.fn().mockResolvedValueOnce([mockProject]),
      }),
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/projects",
      payload: { name: "Test Project" },
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.project.name).toBe("Test Project");
  });

  it("POST /api/projects rejects empty name", async () => {
    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/projects",
      payload: { name: "" },
    });
    expect(res.statusCode).toBe(422);
  });

  it("GET /api/projects/:id returns project", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject);

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/projects/proj-1" });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.project.id).toBe("proj-1");
  });

  it("GET /api/projects/:id returns 404 for missing project", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(undefined);

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/projects/proj-999" });
    expect(res.statusCode).toBe(404);
  });

  it("GET /api/projects/:id returns 403 for other user's project", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce({
      ...mockProject,
      userId: "other-user-id",
    });

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/projects/proj-1" });
    expect(res.statusCode).toBe(403);
  });

  it("GET /api/projects/:id/style returns cached analysis", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce({
      ...mockProject,
      referenceAssetId: "ref-1",
      styleAnalysis: { color_palette: ["#000000"], contrast_level: 1.2 },
    });

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/projects/proj-1/style" });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.styleAnalysis.color_palette).toEqual(["#000000"]);
  });

  it("GET /api/projects/:id/style fetches from Temporal workflow when not cached", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce({
      ...mockProject,
      referenceAssetId: "ref-1",
      styleAnalysis: null,
    });
    vi.mocked(getStyleAnalysisFromWorkflow).mockResolvedValueOnce({
      color_palette: ["#ffffff"],
    });
    vi.mocked(db.update).mockReturnValueOnce({
      set: vi.fn().mockReturnValueOnce({
        where: vi.fn().mockResolvedValueOnce(undefined),
      }),
    } as any);

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/projects/proj-1/style" });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.styleAnalysis.color_palette).toEqual(["#ffffff"]);
  });

  it("GET /api/projects/:id/style returns 202 when analysis is pending", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce({
      ...mockProject,
      referenceAssetId: "ref-1",
      styleAnalysis: null,
    });
    vi.mocked(getStyleAnalysisFromWorkflow).mockResolvedValueOnce(null);

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/projects/proj-1/style" });
    expect(res.statusCode).toBe(202);
  });

  it("PATCH /api/projects/:id updates project", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject);
    vi.mocked(db.update).mockReturnValueOnce({
      set: vi.fn().mockReturnValueOnce({
        where: vi.fn().mockReturnValueOnce({
          returning: vi.fn().mockResolvedValueOnce([{ ...mockProject, name: "Updated" }]),
        }),
      }),
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "PATCH",
      url: "/api/projects/proj-1",
      payload: { name: "Updated" },
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.project.name).toBe("Updated");
  });

  it("PATCH /api/projects/:id toggles excludeFromLearning", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject);
    vi.mocked(db.update).mockReturnValueOnce({
      set: vi.fn().mockReturnValueOnce({
        where: vi.fn().mockReturnValueOnce({
          returning: vi.fn().mockResolvedValueOnce([{ ...mockProject, excludeFromLearning: true }]),
        }),
      }),
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "PATCH",
      url: "/api/projects/proj-1",
      payload: { excludeFromLearning: true },
    });
    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).project.excludeFromLearning).toBe(true);
  });

  it("DELETE /api/projects/:id deletes project", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject);
    vi.mocked(db.delete).mockReturnValueOnce({
      where: vi.fn().mockResolvedValueOnce(undefined),
    } as any);

    const app = await buildApp();
    const res = await app.inject({ method: "DELETE", url: "/api/projects/proj-1" });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.success).toBe(true);
  });

  it("DELETE /api/projects/:id returns 404 for missing project", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(undefined);

    const app = await buildApp();
    const res = await app.inject({ method: "DELETE", url: "/api/projects/proj-999" });
    expect(res.statusCode).toBe(404);
  });

  it("DELETE /api/projects/:id returns 403 for other user's project", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce({
      ...mockProject,
      userId: "other-user-id",
    });

    const app = await buildApp();
    const res = await app.inject({ method: "DELETE", url: "/api/projects/proj-1" });
    expect(res.statusCode).toBe(403);
  });

  it("POST /api/projects defaults styleTier to a valid enum value", async () => {
    const capture: { styleTier?: string } = {};
    vi.mocked(db.insert).mockReturnValueOnce({
      values: vi.fn().mockImplementation((values) => {
        capture.styleTier = values.styleTier;
        return {
          returning: vi.fn().mockResolvedValueOnce([{ ...mockProject, styleTier: values.styleTier }]),
        };
      }),
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/projects",
      payload: { name: "Test Project" },
    });
    expect(res.statusCode).toBe(200);
    expect(capture.styleTier).toBe("with_effects");
    const validTiers = ["cuts_only", "color_grade", "with_text", "with_effects", "full_remix"];
    expect(validTiers).toContain(capture.styleTier);
  });

  it("invalidates the project list cache on create, update, and delete", async () => {
    const cacheDelSpy = vi.spyOn(cache, "cacheDel").mockResolvedValue(undefined);

    vi.mocked(db.insert).mockReturnValueOnce({
      values: vi.fn().mockReturnValueOnce({
        returning: vi.fn().mockResolvedValueOnce([mockProject]),
      }),
    } as any);

    const app = await buildApp();
    await app.inject({ method: "POST", url: "/api/projects", payload: { name: "Test" } });
    expect(cacheDelSpy).toHaveBeenCalledWith("projects:list:test-user-id");

    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject);
    vi.mocked(db.update).mockReturnValueOnce({
      set: vi.fn().mockReturnValueOnce({
        where: vi.fn().mockReturnValueOnce({
          returning: vi.fn().mockResolvedValueOnce([{ ...mockProject, name: "Updated" }]),
        }),
      }),
    } as any);
    await app.inject({ method: "PATCH", url: "/api/projects/proj-1", payload: { name: "Updated" } });
    expect(cacheDelSpy).toHaveBeenCalledWith("projects:list:test-user-id");

    vi.mocked(db.delete).mockReturnValueOnce({
      where: vi.fn().mockResolvedValueOnce(undefined),
    } as any);
    await app.inject({ method: "DELETE", url: "/api/projects/proj-1" });
    expect(cacheDelSpy).toHaveBeenCalledWith("projects:list:test-user-id");
  });
});
