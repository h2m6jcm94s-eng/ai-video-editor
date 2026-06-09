import { describe, it, expect, vi, beforeEach } from "vitest";
import { buildApp } from "../app";
import { redis } from "../lib/redis";
import { countTokens } from "../lib/tokens";

describe("Token Budget Middleware", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("GET /api/settings/usage returns usage data", async () => {
    const app = await buildApp();
    const res = await app.inject({
      method: "GET",
      url: "/api/settings/usage",
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body).toHaveProperty("dailyUsage");
    expect(body).toHaveProperty("dailyLimit");
    expect(body).toHaveProperty("remaining");
    expect(body).toHaveProperty("resetAt");
  });

  it("counts tokens accurately", async () => {
    const tokens = await countTokens("Hello world");
    expect(tokens).toBeGreaterThan(0);
    expect(await countTokens("")).toBe(0);
  });

  it("metrics endpoint includes token counters", async () => {
    const app = await buildApp();
    const metricsRes = await app.inject({ method: "GET", url: "/api/metrics" });
    expect(metricsRes.statusCode).toBe(200);
    expect(metricsRes.body).toContain("ave_tokens_consumed_total");
    expect(metricsRes.body).toContain("ave_budget_violations_total");
  });
});
