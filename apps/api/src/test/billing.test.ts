import { describe, expect, it } from "vitest";
import { buildApp } from "../app";

describe("Billing Routes", () => {
  it("GET /api/billing/plan returns mock subscription", async () => {
    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/billing/plan" });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.subscription.plan).toBe("pro");
    expect(body.subscription.status).toBe("active");
  });

  it("GET /api/billing/invoices returns mock invoices", async () => {
    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/billing/invoices" });
    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).invoices.length).toBeGreaterThan(0);
  });

  it("POST /api/billing/checkout returns mock session", async () => {
    const app = await buildApp();
    const res = await app.inject({ method: "POST", url: "/api/billing/checkout" });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.sessionId).toMatch(/^mock_session/);
    expect(body.url).toContain("/settings/billing");
  });

  it("POST /api/billing/portal returns mock portal url", async () => {
    const app = await buildApp();
    const res = await app.inject({ method: "POST", url: "/api/billing/portal" });
    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).url).toContain("/settings/billing");
  });

  it("POST /api/billing/webhook is unauthenticated and acks", async () => {
    const app = await buildApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/billing/webhook",
      payload: { type: "invoice.paid" },
    });
    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).received).toBe(true);
  });
});
