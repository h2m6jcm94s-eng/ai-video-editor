import { clerkClient } from "@clerk/fastify";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";

function mockAdmin() {
  vi.mocked(clerkClient.users.getUser).mockResolvedValue({
    id: "admin-user-id",
    emailAddresses: [{ emailAddress: "admin@test.com" }],
    fullName: "Admin User",
    publicMetadata: { role: "admin" },
  } as any);
}

describe("Admin Routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAdmin();
  });

  it("GET /api/admin/users/:userId returns user stats", async () => {
    vi.mocked(db.query.users.findFirst).mockResolvedValueOnce({
      id: "user-1",
      clerkId: "clerk-user-1",
      email: "user@test.com",
      name: "User",
      createdAt: new Date(),
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "GET",
      url: "/api/admin/users/user-1",
    });

    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.user.id).toBe("user-1");
    expect(body.stats).toEqual({ errors: 0, projects: 0, renders: 0 });
  });

  it("GET /api/admin/users/:userId handles users with multiple projects", async () => {
    vi.mocked(db.query.users.findFirst).mockResolvedValueOnce({
      id: "user-2",
      clerkId: "clerk-user-2",
      email: "multi@test.com",
      name: "Multi Project User",
      createdAt: new Date(),
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "GET",
      url: "/api/admin/users/user-2",
    });

    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.user.id).toBe("user-2");
    expect(body.stats.renders).toBe(0);
  });

  it("GET /api/admin/users/:userId returns 404 for missing user", async () => {
    vi.mocked(db.query.users.findFirst).mockResolvedValueOnce(undefined);

    const app = await buildApp();
    const res = await app.inject({
      method: "GET",
      url: "/api/admin/users/missing",
    });
    expect(res.statusCode).toBe(404);
  });
});
