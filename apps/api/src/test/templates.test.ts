import { describe, it, expect, vi, beforeEach } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";

describe("Template Routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockTemplate = {
    id: "tmpl-1",
    userId: "test-user-id",
    name: "Cinematic Intro",
    description: "A dramatic opening",
    cutList: {
      globals: { totalDurationS: 10, tempoBpm: 120 },
      slots: [{ index: 0, startS: 0, durationS: 5, beatIndex: 0, section: "intro", targetShotType: "medium", subjectHint: "person", motionHint: "static" }],
    },
    tags: ["intro", "cinematic"],
    isPublic: true,
    usageCount: 5,
    createdAt: new Date(),
    updatedAt: new Date(),
  };

  it("GET /api/templates lists templates", async () => {
    vi.mocked(db.query.templates.findMany).mockResolvedValueOnce([mockTemplate]);

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/templates" });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.templates).toHaveLength(1);
    expect(body.templates[0].name).toBe("Cinematic Intro");
  });

  it("POST /api/templates creates a template", async () => {
    vi.mocked(db.insert).mockReturnValueOnce({
      values: vi.fn().mockReturnValueOnce({
        returning: vi.fn().mockResolvedValueOnce([mockTemplate]),
      }),
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/templates",
      payload: {
        name: "Cinematic Intro",
        cutList: {
          globals: { totalDurationS: 10, tempoBpm: 120 },
          slots: [{ index: 0, startS: 0, durationS: 5, beatIndex: 0, section: "intro", targetShotType: "medium", subjectHint: "person", motionHint: "static" }],
        },
      },
    });
    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).template.name).toBe("Cinematic Intro");
  });

  it("POST rejects invalid body", async () => {
    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/templates",
      payload: { name: "" },
    });
    expect(res.statusCode).toBe(422);
  });

  it("GET /api/templates/:id returns template", async () => {
    vi.mocked(db.query.templates.findFirst).mockResolvedValueOnce(mockTemplate);

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/templates/tmpl-1" });
    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).template.id).toBe("tmpl-1");
  });

  it("GET /api/templates/:id returns 404 for missing", async () => {
    vi.mocked(db.query.templates.findFirst).mockResolvedValueOnce(undefined);

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/templates/tmpl-999" });
    expect(res.statusCode).toBe(404);
  });

  it("GET /api/templates/:id returns 403 for private template of other user", async () => {
    vi.mocked(db.query.templates.findFirst).mockResolvedValueOnce({
      ...mockTemplate,
      userId: "other-user-id",
      isPublic: false,
    });

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/templates/tmpl-1" });
    expect(res.statusCode).toBe(403);
  });

  it("PATCH /api/templates/:id updates template", async () => {
    vi.mocked(db.query.templates.findFirst).mockResolvedValueOnce(mockTemplate);
    vi.mocked(db.update).mockReturnValueOnce({
      set: vi.fn().mockReturnValueOnce({
        where: vi.fn().mockReturnValueOnce({
          returning: vi.fn().mockResolvedValueOnce([{ ...mockTemplate, name: "Updated" }]),
        }),
      }),
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "PATCH",
      url: "/api/templates/tmpl-1",
      payload: { name: "Updated" },
    });
    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).template.name).toBe("Updated");
  });

  it("PATCH /api/templates/:id returns 404 for missing template", async () => {
    vi.mocked(db.query.templates.findFirst).mockResolvedValueOnce(undefined);

    const app = await buildApp();
    const res = await app.inject({
      method: "PATCH",
      url: "/api/templates/tmpl-999",
      payload: { name: "Updated" },
    });
    expect(res.statusCode).toBe(404);
  });

  it("PATCH /api/templates/:id returns 403 for other user's template", async () => {
    vi.mocked(db.query.templates.findFirst).mockResolvedValueOnce({
      ...mockTemplate,
      userId: "other-user-id",
    });

    const app = await buildApp();
    const res = await app.inject({
      method: "PATCH",
      url: "/api/templates/tmpl-1",
      payload: { name: "Updated" },
    });
    expect(res.statusCode).toBe(403);
  });

  it("DELETE /api/templates/:id deletes template", async () => {
    vi.mocked(db.query.templates.findFirst).mockResolvedValueOnce(mockTemplate);
    vi.mocked(db.delete).mockReturnValueOnce({
      where: vi.fn().mockResolvedValueOnce(undefined),
    } as any);

    const app = await buildApp();
    const res = await app.inject({ method: "DELETE", url: "/api/templates/tmpl-1" });
    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).success).toBe(true);
  });

  it("DELETE /api/templates/:id returns 404 for missing template", async () => {
    vi.mocked(db.query.templates.findFirst).mockResolvedValueOnce(undefined);

    const app = await buildApp();
    const res = await app.inject({ method: "DELETE", url: "/api/templates/tmpl-999" });
    expect(res.statusCode).toBe(404);
  });

  it("DELETE /api/templates/:id returns 403 for other user's template", async () => {
    vi.mocked(db.query.templates.findFirst).mockResolvedValueOnce({
      ...mockTemplate,
      userId: "other-user-id",
    });

    const app = await buildApp();
    const res = await app.inject({ method: "DELETE", url: "/api/templates/tmpl-1" });
    expect(res.statusCode).toBe(403);
  });

  it("POST /api/templates/:id/apply returns cutList and increments usage", async () => {
    vi.mocked(db.query.templates.findFirst).mockResolvedValueOnce(mockTemplate);
    vi.mocked(db.update).mockReturnValueOnce({
      set: vi.fn().mockReturnValueOnce({
        where: vi.fn().mockResolvedValueOnce(undefined),
      }),
    } as any);

    const app = await buildApp();
    const res = await app.inject({ method: "POST", url: "/api/templates/tmpl-1/apply" });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.cutList).toEqual(mockTemplate.cutList);
  });

  it("apply returns 403 for private template of other user", async () => {
    vi.mocked(db.query.templates.findFirst).mockResolvedValueOnce({
      ...mockTemplate,
      userId: "other-user-id",
      isPublic: false,
    });

    const app = await buildApp();
    const res = await app.inject({ method: "POST", url: "/api/templates/tmpl-1/apply" });
    expect(res.statusCode).toBe(403);
  });

  it("POST /api/templates/:id/apply returns 404 for missing template", async () => {
    vi.mocked(db.query.templates.findFirst).mockResolvedValueOnce(undefined);

    const app = await buildApp();
    const res = await app.inject({ method: "POST", url: "/api/templates/tmpl-999/apply" });
    expect(res.statusCode).toBe(404);
  });
});
