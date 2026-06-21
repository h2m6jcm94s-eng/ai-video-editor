import { beforeEach, describe, expect, it, vi } from "vitest";
import { sendError } from "../lib/errors";
import { recordUserEvent } from "../lib/userEvents";

vi.mock("../lib/userEvents", () => ({
  recordUserEvent: vi.fn().mockResolvedValue(undefined),
}));

function makeReply(overrides?: { userId?: string }) {
  return {
    request: {
      userId: overrides?.userId,
      routeOptions: { url: "/api/test" },
      log: { warn: vi.fn(), error: vi.fn() },
    },
    status: vi.fn().mockReturnThis(),
    send: vi.fn().mockReturnThis(),
  } as unknown as import("fastify").FastifyReply;
}

describe("sendError", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("records a user event when userId is present", async () => {
    const reply = makeReply({ userId: "user-1" });
    sendError(reply, 400, "Bad request", "VALIDATION_ERROR");

    expect(recordUserEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        userId: "user-1",
        code: "VALIDATION_ERROR",
        message: "Bad request",
      }),
    );
  });

  it("logs and increments a metric when event recording fails", async () => {
    const err = new Error("DB down");
    vi.mocked(recordUserEvent).mockRejectedValueOnce(err);

    const reply = makeReply({ userId: "user-1" });
    sendError(reply, 500, "Server error", "INTERNAL_ERROR");

    // Give the fire-and-forget promise a tick to settle.
    await new Promise((r) => setTimeout(r, 0));

    expect(reply.request.log.warn).toHaveBeenCalledWith(
      expect.objectContaining({ err, userId: "user-1", code: "INTERNAL_ERROR" }),
      "Failed to record user error event",
    );
  });

  it("does not record an event when userId is missing", async () => {
    const reply = makeReply();
    sendError(reply, 401, "Unauthorized", "UNAUTHORIZED");

    expect(recordUserEvent).not.toHaveBeenCalled();
  });
});
