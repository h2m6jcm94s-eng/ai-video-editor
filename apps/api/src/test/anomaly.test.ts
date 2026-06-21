import { clerkClient } from "@clerk/fastify";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { buildApp } from "../app";
import * as anomaly from "../services/anomaly";

function mockAdmin() {
  vi.mocked(clerkClient.users.getUser).mockResolvedValue({
    id: "test-user-id",
    emailAddresses: [{ emailAddress: "admin@test.com" }],
    fullName: "Admin User",
    publicMetadata: { role: "admin" },
  } as any);
}

describe("Anomaly Routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAdmin();
  });

  it("GET /api/anomalies returns recent anomalies", async () => {
    vi.spyOn(anomaly, "listRecentAnomalies").mockResolvedValueOnce([
      {
        userId: "user-1",
        metric: "req:/api/projects/:id/prompt",
        value: 50,
        expected: 5,
        zScore: 4.5,
        timestamp: new Date().toISOString(),
      },
    ]);

    const app = await buildApp();
    const res = await app.inject({
      method: "GET",
      url: "/api/anomalies",
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.anomalies).toHaveLength(1);
    expect(body.anomalies[0].metric).toBe("req:/api/projects/:id/prompt");
  });

  it("GET /api/anomalies returns empty array when no anomalies", async () => {
    vi.spyOn(anomaly, "listRecentAnomalies").mockResolvedValueOnce([]);

    const app = await buildApp();
    const res = await app.inject({
      method: "GET",
      url: "/api/anomalies",
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.anomalies).toHaveLength(0);
  });

  it("GET /api/anomalies rejects non-admin users", async () => {
    vi.mocked(clerkClient.users.getUser).mockResolvedValue({
      id: "test-user-id",
      emailAddresses: [{ emailAddress: "test@test.com" }],
      fullName: "Test User",
      publicMetadata: { role: "user" },
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "GET",
      url: "/api/anomalies",
    });
    expect(res.statusCode).toBe(403);
    expect(JSON.parse(res.body).code).toBe("FORBIDDEN");
  });
});

describe("Anomaly Detection Service", () => {
  it("recordNumericMetric returns null with few samples", async () => {
    const result = await anomaly.recordNumericMetric("user-1", "render_time", 100);
    expect(result).toBeNull();
  });
});
