import { beforeEach, describe, expect, it, vi } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";
import * as rateLimit from "../lib/rateLimit";
import { redis } from "../lib/redis";

describe("Sliding Window Rate Limit", () => {
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

  it("returns 429 when sliding window rejects", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject);
    vi.spyOn(rateLimit, "slidingWindowCheck").mockResolvedValueOnce({
      allowed: false,
      remaining: 0,
      resetMs: Date.now() + 30000,
      limit: 10,
      windowMs: 60000,
    });

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/projects/proj-1/prompt",
      payload: { prompt: "test" },
    });
    expect(res.statusCode).toBe(429);
    const body = JSON.parse(res.body);
    expect(body.code).toBe("RATE_LIMITED");
    expect(body.details).toBeDefined();
  });

  it("allows request when sliding window permits", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce({
        json: async () => ({
          content: [{ type: "text", text: JSON.stringify({ diff: [], explanation: "OK" }) }],
        }),
        ok: true,
        status: 200,
      }),
    );
    vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
    vi.stubEnv("AI_PROVIDER", "claude");

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/projects/proj-1/prompt",
      payload: { prompt: "test" },
    });
    expect(res.statusCode).toBe(200);
  });

  describe("slidingWindowCheck Redis error handling", () => {
    it("fails open by default when Redis throws", async () => {
      vi.mocked(redis.zremrangebyscore).mockRejectedValueOnce(new Error("Redis down"));

      const result = await rateLimit.slidingWindowCheck({
        key: "rl:read:user-1",
        limit: 10,
        windowMs: 60_000,
      });

      expect(result.allowed).toBe(true);
    });

    it("fails closed for expensive/mutating endpoints when Redis throws", async () => {
      vi.mocked(redis.zremrangebyscore).mockRejectedValueOnce(new Error("Redis down"));

      const result = await rateLimit.slidingWindowCheck({
        key: "rl:prompt:user-1",
        limit: 10,
        windowMs: 60_000,
        failClosed: true,
      });

      expect(result.allowed).toBe(false);
    });
  });
});
