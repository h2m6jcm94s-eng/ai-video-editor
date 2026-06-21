import { beforeEach, describe, expect, it, vi } from "vitest";
import { db } from "../../db";
import { recordUserEvent } from "../../lib/userEvents";

describe("recordUserEvent", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("inserts a new user event with raw details", async () => {
    vi.mocked(db.query.userEvents.findFirst).mockResolvedValueOnce(undefined);
    vi.mocked(db.select).mockReturnValueOnce({
      from: vi.fn().mockReturnValueOnce({
        where: vi.fn().mockReturnValueOnce([{ unackedCount: 0 }]),
      }),
    } as any);
    const valuesFn = vi.fn().mockReturnValueOnce({
      returning: vi.fn().mockResolvedValueOnce([{ id: "evt-1" }]),
    });
    vi.mocked(db.insert).mockReturnValueOnce({ values: valuesFn } as any);

    await recordUserEvent({
      userId: "user-1",
      code: "INTERNAL_ERROR",
      message: "Something went wrong",
      route: "/api/projects",
      details: { field: "value", nested: { count: 1 } },
    });

    expect(valuesFn).toHaveBeenCalledWith(
      expect.objectContaining({
        details: { field: "value", nested: { count: 1 } },
      }),
    );
  });

  it("increments occurrence_count on duplicate within 5min", async () => {
    const existingEvent = {
      id: "evt-1",
      userId: "user-1",
      code: "INTERNAL_ERROR",
      message: "Something went wrong",
      occurrenceCount: 1,
      createdAt: new Date(),
    };
    vi.mocked(db.query.userEvents.findFirst).mockResolvedValueOnce(existingEvent as any);
    vi.mocked(db.update).mockReturnValueOnce({
      set: vi.fn().mockReturnValueOnce({
        where: vi.fn().mockReturnValueOnce({
          returning: vi.fn().mockResolvedValueOnce([{ occurrenceCount: 2 }]),
        }),
      }),
    } as any);

    await recordUserEvent({
      userId: "user-1",
      code: "INTERNAL_ERROR",
      message: "Something went wrong",
    });

    expect(db.update).toHaveBeenCalled();
  });

  it("skips UNAUTHORIZED errors", async () => {
    await recordUserEvent({
      userId: "user-1",
      code: "UNAUTHORIZED",
      message: "Sign in required",
    });

    expect(db.insert).not.toHaveBeenCalled();
    expect(db.update).not.toHaveBeenCalled();
  });

  it("marks oldest event dropped when cap exceeded", async () => {
    vi.mocked(db.query.userEvents.findFirst).mockResolvedValueOnce(undefined);
    vi.mocked(db.select).mockReturnValueOnce({
      from: vi.fn().mockReturnValueOnce({
        where: vi.fn().mockReturnValueOnce([{ unackedCount: 50 }]),
      }),
    } as any);
    vi.mocked(db.select).mockReturnValueOnce({
      from: vi.fn().mockReturnValueOnce({
        where: vi.fn().mockReturnValueOnce({
          orderBy: vi.fn().mockReturnValueOnce({
            limit: vi.fn().mockReturnValueOnce([{ id: "oldest-evt" }]),
          }),
        }),
      }),
    } as any);
    vi.mocked(db.update).mockReturnValueOnce({
      set: vi.fn().mockReturnValueOnce({
        where: vi.fn().mockReturnValueOnce({
          returning: vi.fn().mockResolvedValueOnce([{ dropped: true }]),
        }),
      }),
    } as any);
    vi.mocked(db.insert).mockReturnValueOnce({
      values: vi.fn().mockReturnValueOnce({
        returning: vi.fn().mockResolvedValueOnce([{ id: "new-evt" }]),
      }),
    } as any);

    await recordUserEvent({
      userId: "user-1",
      code: "INTERNAL_ERROR",
      message: "New error",
    });

    // Should have called update (to mark oldest dropped) and insert (new event)
    expect(db.update).toHaveBeenCalled();
    expect(db.insert).toHaveBeenCalled();
  });

  it("never throws even when DB fails", async () => {
    vi.mocked(db.query.userEvents.findFirst).mockRejectedValueOnce(new Error("DB down"));

    await expect(
      recordUserEvent({
        userId: "user-1",
        code: "INTERNAL_ERROR",
        message: "Test",
      }),
    ).resolves.not.toThrow();
  });
});
