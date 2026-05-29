// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { createClerkClient } from "@clerk/fastify";
import type { FastifyRequest, FastifyReply } from "fastify";

const clerk = createClerkClient({
  secretKey: process.env.CLERK_SECRET_KEY!,
});

export async function requireAuth(
  request: FastifyRequest,
  reply: FastifyReply
) {
  const state = await clerk.authenticateRequest(request.raw as any, {
    secretKey: process.env.CLERK_SECRET_KEY,
  });
  if (!state.isSignedIn) {
    return reply.status(401).send({ error: "Unauthorized", code: "UNAUTHORIZED" });
  }
  const auth = state.toAuth();
  request.auth = auth;
  request.userId = auth.userId;
}
