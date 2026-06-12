import { describe, expect, it, vi } from "vitest";
import { buildApp } from "../app";
import { recordUserEvent } from "../lib/userEvents";

vi.mock("../lib/userEvents", () => ({
  recordUserEvent: vi.fn(),
}));

describe("Internal Routes", () => {
  it("POST /api/internal/user-events returns 422 on invalid payload", async () => {
    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/internal/user-events",
      payload: { userId: "not-a-uuid", code: "", message: "" },
      headers: { "x-internal-token": process.env.INTERNAL_WORKER_TOKEN },
    });

    expect(res.statusCode).toBe(422);
    const body = JSON.parse(res.body);
    expect(body.code).toBe("VALIDATION_ERROR");
    // The invalid payload should not have been recorded as a user event.
    expect(recordUserEvent).not.toHaveBeenCalledWith(expect.objectContaining({ userId: "not-a-uuid" }));
  });

  it("POST /api/internal/user-events records a valid event", async () => {
    vi.mocked(recordUserEvent).mockResolvedValueOnce(undefined);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/internal/user-events",
      payload: {
        userId: "550e8400-e29b-41d4-a716-446655440000",
        code: "TEST_EVENT",
        message: "Something happened",
      },
      headers: { "x-internal-token": process.env.INTERNAL_WORKER_TOKEN },
    });

    expect(res.statusCode).toBe(200);
    expect(recordUserEvent).toHaveBeenCalled();
  });
});
