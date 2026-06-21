import { beforeEach, describe, expect, it, vi } from "vitest";
import { buildApp } from "../app";

describe("Log Routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("POST /api/log accepts a valid batch", async () => {
    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/log",
      payload: {
        events: [{ level: "info", message: "hello", ts: Date.now(), url: "/", context: { a: 1 } }],
      },
    });
    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).ok).toBe(true);
  });

  it("POST /api/log rejects batches over 100 events", async () => {
    const app = await buildApp();
    const events = Array.from({ length: 101 }, (_, i) => ({
      level: "info" as const,
      message: `event ${i}`,
      ts: Date.now(),
      url: "/",
    }));
    const res = await app.inject({
      method: "POST",
      url: "/api/log",
      payload: { events },
    });
    expect(res.statusCode).toBe(422);
    expect(JSON.parse(res.body).code).toBe("VALIDATION_ERROR");
  });

  it("POST /api/log rejects invalid event shapes", async () => {
    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/log",
      payload: { events: [{ level: "info", ts: Date.now(), url: "/" }] },
    });
    expect(res.statusCode).toBe(422);
    expect(JSON.parse(res.body).code).toBe("VALIDATION_ERROR");
  });
});
