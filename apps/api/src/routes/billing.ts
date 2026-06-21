// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
/**
 * Hardcoded/mock billing routes for showcase builds.
 * Replace with real Stripe integration when ready.
 */

import type { FastifyInstance } from "fastify";
import { requireAuth } from "../middleware/auth";

const MOCK_PLAN = {
  plan: "pro",
  status: "active",
  currentPeriodEnd: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
  features: ["Unlimited projects", "4K exports", "AI generation", "All effects", "Priority rendering"],
};

const MOCK_INVOICES = [
  {
    id: "inv_1",
    amount: 2900,
    currency: "usd",
    status: "paid",
    createdAt: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: "inv_2",
    amount: 2900,
    currency: "usd",
    status: "paid",
    createdAt: new Date(Date.now() - 60 * 24 * 60 * 60 * 1000).toISOString(),
  },
];

export async function billingRoutes(app: FastifyInstance) {
  // Stripe-style webhook seam — unauthenticated so a future provider can POST here.
  app.post("/webhook", async () => {
    return { received: true };
  });

  // Everything below this point requires a logged-in user.
  app.addHook("onRequest", requireAuth);

  app.get("/plan", async () => {
    return { subscription: MOCK_PLAN };
  });

  app.get("/invoices", async () => {
    return { invoices: MOCK_INVOICES };
  });

  app.post("/checkout", async () => {
    return {
      sessionId: "mock_session_123",
      url: `${process.env.WEB_URL || "http://localhost:3000"}/settings/billing?success=1`,
    };
  });

  app.post("/portal", async () => {
    return {
      url: `${process.env.WEB_URL || "http://localhost:3000"}/settings/billing`,
    };
  });
}
