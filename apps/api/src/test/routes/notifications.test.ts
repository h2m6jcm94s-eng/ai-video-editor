import { beforeEach, describe, expect, it, vi } from "vitest";
import { buildApp } from "../../app";
import { db } from "../../db";

describe("Notification Routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("lists notifications for authenticated user", async () => {
    const app = await buildApp();
    vi.mocked(db.query.userEvents.findMany).mockResolvedValueOnce([
      {
        id: "evt-1",
        userId: "test-user-id",
        code: "INTERNAL_ERROR",
        message: "Oops",
        occurrenceCount: 1,
        acknowledged: false,
        dropped: false,
        createdAt: new Date(),
        updatedAt: new Date(),
      },
    ]);

    const res = await app.inject({
      method: "GET",
      url: "/api/notifications",
    });

    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.items).toHaveLength(1);
    expect(body.items[0].code).toBe("INTERNAL_ERROR");
  });

  it("acknowledges a notification", async () => {
    const app = await buildApp();
    vi.mocked(db.update).mockReturnValueOnce({
      set: vi.fn().mockReturnValueOnce({
        where: vi.fn().mockReturnValueOnce({
          returning: vi.fn().mockResolvedValueOnce([{ id: "evt-1", acknowledged: true }]),
        }),
      }),
    } as any);

    const res = await app.inject({
      method: "POST",
      url: "/api/notifications/evt-1/ack",
    });

    expect(res.statusCode).toBe(200);
    expect(res.json().ok).toBe(true);
  });

  it("acknowledges all notifications", async () => {
    const app = await buildApp();
    vi.mocked(db.update).mockReturnValueOnce({
      set: vi.fn().mockReturnValueOnce({
        where: vi.fn().mockReturnValueOnce({
          returning: vi.fn().mockResolvedValueOnce([]),
        }),
      }),
    } as any);

    const res = await app.inject({
      method: "POST",
      url: "/api/notifications/ack-all",
    });

    expect(res.statusCode).toBe(200);
    expect(res.json().ok).toBe(true);
  });
});
