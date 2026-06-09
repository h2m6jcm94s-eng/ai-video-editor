import { describe, it, expect, vi, beforeEach } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";

describe("Auth Middleware", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 401 when Clerk reports not signed in", async () => {
    vi.resetModules();
    const clerkMock = {
      authenticateRequest: vi.fn().mockResolvedValue({
        isSignedIn: false,
        toAuth: () => ({ userId: "" }),
      }),
    };
    vi.doMock("@clerk/fastify", () => ({
      createClerkClient: vi.fn(() => clerkMock),
      clerkClient: {
        users: {
          getUser: vi.fn(async () => ({
            id: "test-user-id",
            emailAddresses: [{ emailAddress: "test@test.com" }],
            fullName: "Test User",
          })),
        },
      },
    }));

    const { buildApp: buildAppFresh } = await import("../app");
    const app = await buildAppFresh();
    const res = await app.inject({ method: "GET", url: "/api/projects" });
    expect(res.statusCode).toBe(401);
    expect(JSON.parse(res.body).code).toBe("UNAUTHORIZED");
  });

  it("creates new local user when Clerk user not in DB", async () => {
    const { getUserByClerkId, upsertUser } = await import("../services/users");
    vi.mocked(getUserByClerkId).mockResolvedValueOnce(null);
    vi.mocked(upsertUser).mockResolvedValueOnce({
      id: "new-local-id",
      clerkId: "test-user-id",
      email: "test@test.com",
      name: "Test User",
    });

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/projects" });
    expect(res.statusCode).toBe(200);
    expect(upsertUser).toHaveBeenCalled();
  });

  it("uses placeholder when Clerk API lookup fails", async () => {
    const { getUserByClerkId, upsertUser } = await import("../services/users");
    const { clerkClient } = await import("@clerk/fastify");
    vi.mocked(getUserByClerkId).mockResolvedValueOnce(null);
    vi.mocked(clerkClient.users.getUser).mockRejectedValueOnce(new Error("Clerk API error"));
    vi.mocked(upsertUser).mockResolvedValueOnce({
      id: "placeholder-id",
      clerkId: "test-user-id",
      email: "test-user-id@placeholder.local",
      name: "User",
    });

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/projects" });
    expect(res.statusCode).toBe(200);
    expect(upsertUser).toHaveBeenCalled();
  });

  it("returns 500 when user resolution fails", async () => {
    const { getUserByClerkId } = await import("../services/users");
    vi.mocked(getUserByClerkId).mockRejectedValueOnce(new Error("DB connection lost"));

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/projects" });
    expect(res.statusCode).toBe(500);
    expect(JSON.parse(res.body).code).toBe("USER_RESOLUTION_ERROR");
  });
});
