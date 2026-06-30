import { beforeEach, describe, expect, it, vi } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";

describe("User taste profile routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("GET /api/user-taste-profile returns profile", async () => {
    vi.mocked(db.query.userTasteProfiles.findFirst).mockResolvedValueOnce({
      id: "profile-1",
      userId: "test-user-id",
      contributeToGlobalCorpus: true,
    } as any);

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/user-taste-profile" });
    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).profile.contributeToGlobalCorpus).toBe(true);
  });

  it("PATCH /api/user-taste-profile updates privacy flag", async () => {
    vi.mocked(db.query.userTasteProfiles.findFirst).mockResolvedValueOnce({
      id: "profile-1",
      userId: "test-user-id",
      contributeToGlobalCorpus: true,
    } as any);
    vi.mocked(db.update).mockReturnValueOnce({
      set: vi.fn().mockReturnValueOnce({
        where: vi.fn().mockReturnValueOnce({
          returning: vi.fn().mockResolvedValueOnce([{ id: "profile-1", contributeToGlobalCorpus: false }]),
        }),
      }),
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "PATCH",
      url: "/api/user-taste-profile",
      payload: { contributeToGlobalCorpus: false },
    });

    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).profile.contributeToGlobalCorpus).toBe(false);
  });
});
