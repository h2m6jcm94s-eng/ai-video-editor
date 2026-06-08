import { describe, it, expect, vi, beforeEach } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";

describe("Upload contract tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockProject = {
    id: "proj-1",
    userId: "test-user-id",
  };

  it("POST /api/uploads/presigned rejects invalid MIME type", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/uploads/presigned",
      payload: {
        projectId: "proj-1",
        filename: "virus.exe",
        mimeType: "application/x-msdownload",
        type: "clip",
      },
    });

    expect(res.statusCode).toBe(422);
    expect(JSON.parse(res.body).code).toBe("VALIDATION_ERROR");
  });

  it("POST /api/uploads/presigned rejects invalid asset type", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/uploads/presigned",
      payload: {
        projectId: "proj-1",
        filename: "video.mp4",
        mimeType: "video/mp4",
        type: "not_a_type",
      },
    });

    expect(res.statusCode).toBe(422);
    expect(JSON.parse(res.body).code).toBe("VALIDATION_ERROR");
  });

  it("POST /api/uploads/presigned rejects empty filename", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/uploads/presigned",
      payload: {
        projectId: "proj-1",
        filename: "",
        mimeType: "video/mp4",
        type: "clip",
      },
    });

    expect(res.statusCode).toBe(422);
    expect(JSON.parse(res.body).code).toBe("VALIDATION_ERROR");
  });
});
