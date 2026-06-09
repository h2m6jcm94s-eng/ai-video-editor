import { describe, it, expect } from "vitest";
import { buildApp } from "../../app";

describe("Project route contract tests", () => {
  it("POST /api/projects rejects extra fields when schema is .strict()", async () => {
    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/projects",
      payload: { name: "ok", styleTier: "with_effects", mode: "auto", evil: "extra" },
    });
    expect(res.statusCode).toBe(422);
  });

  it("POST /api/projects rejects snake_case styleTier", async () => {
    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/projects",
      payload: { name: "ok", style_tier: "with_effects", mode: "auto" },
    });
    expect(res.statusCode).toBe(422);
  });

  it("PATCH /api/projects/:id/cutlist rejects snake_case slot keys", async () => {
    const app = await buildApp();
    const res = await app.inject({
      method: "PATCH",
      url: "/api/projects/550e8400-e29b-41d4-a716-446655440000/cutlist",
      payload: {
        cutList: {
          globals: { totalDurationS: 10, tempoBpm: 120, timeSignature: "4/4", energyCurve: [], sectionMarkers: [], aspectRatio: "9:16" },
          slots: [{ start_s: 0, duration_s: 5 }],
          overlays: [],
          audioTracks: [],
        },
      },
    });
    expect(res.statusCode).toBe(422);
  });
});
