import { describe, it, expect, vi, beforeEach } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";

describe("Settings Routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockKeyRow = {
    userId: "test-user-id",
    provider: "anthropic",
    encryptedKey: "+9Pj4+jl6uDk4Q==", // "sk-test-key" XOR with "dev-secret-do-not-use-in-production"
    createdAt: new Date(),
    updatedAt: new Date(),
  };

  it("GET /api/settings/provider-keys lists keys masked", async () => {
    vi.mocked(db.query.providerKeys.findMany).mockResolvedValueOnce([mockKeyRow]);

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/settings/provider-keys" });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.keys).toHaveLength(1);
    expect(body.keys[0].provider).toBe("anthropic");
    expect(body.keys[0].masked).toMatch(/^\*\*\*/);
  });

  it("GET /api/settings/provider-keys returns empty when no keys", async () => {
    vi.mocked(db.query.providerKeys.findMany).mockResolvedValueOnce([]);

    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/settings/provider-keys" });
    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).keys).toEqual([]);
  });

  it("POST /api/settings/provider-keys saves a key", async () => {
    vi.mocked(db.insert).mockReturnValueOnce({
      values: vi.fn().mockReturnValueOnce({
        onConflictDoUpdate: vi.fn().mockResolvedValueOnce(undefined),
      }),
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/settings/provider-keys",
      payload: { provider: "anthropic", key: "sk-test-key" },
    });
    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).success).toBe(true);
  });

  it("POST /api/settings/provider-keys rejects invalid body", async () => {
    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/settings/provider-keys",
      payload: { provider: "" },
    });
    expect(res.statusCode).toBe(422);
  });

  it("DELETE /api/settings/provider-keys/:provider deletes a key", async () => {
    vi.mocked(db.delete).mockReturnValueOnce({
      where: vi.fn().mockResolvedValueOnce(undefined),
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "DELETE",
      url: "/api/settings/provider-keys/anthropic",
    });
    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).success).toBe(true);
  });

  it("POST /api/settings/provider-keys/test returns 404 when key not found", async () => {
    vi.mocked(db.query.providerKeys.findFirst).mockResolvedValueOnce(undefined);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/settings/provider-keys/test",
      payload: { provider: "anthropic" },
    });
    expect(res.statusCode).toBe(404);
    expect(JSON.parse(res.body).code).toBe("NOT_FOUND");
  });

  it("POST /api/settings/provider-keys/test returns 400 for unsupported provider", async () => {
    vi.mocked(db.query.providerKeys.findFirst).mockResolvedValueOnce(mockKeyRow);

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/settings/provider-keys/test",
      payload: { provider: "gemini" },
    });
    expect(res.statusCode).toBe(400);
    expect(JSON.parse(res.body).code).toBe("VALIDATION_ERROR");
  });

  it("POST /api/settings/provider-keys/test succeeds for anthropic", async () => {
    vi.mocked(db.query.providerKeys.findFirst).mockResolvedValueOnce(mockKeyRow);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce({ ok: true, text: vi.fn().mockResolvedValueOnce("") }));

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/settings/provider-keys/test",
      payload: { provider: "anthropic" },
    });
    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).success).toBe(true);
  });

  it("POST /api/settings/provider-keys/test succeeds for openai", async () => {
    vi.mocked(db.query.providerKeys.findFirst).mockResolvedValueOnce({
      ...mockKeyRow,
      provider: "openai",
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce({ ok: true, text: vi.fn().mockResolvedValueOnce("") }));

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/settings/provider-keys/test",
      payload: { provider: "openai" },
    });
    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).success).toBe(true);
  });

  it("POST /api/settings/provider-keys/test handles provider error response", async () => {
    vi.mocked(db.query.providerKeys.findFirst).mockResolvedValueOnce(mockKeyRow);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce({ ok: false, text: vi.fn().mockResolvedValueOnce("invalid key") }));

    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/settings/provider-keys/test",
      payload: { provider: "anthropic" },
    });
    expect(res.statusCode).toBe(400);
    expect(JSON.parse(res.body).code).toBe("PROVIDER_INVALID_RESPONSE");
  });
});
