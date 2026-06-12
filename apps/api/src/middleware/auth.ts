// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { clerkClient, createClerkClient } from "@clerk/fastify";
import type { FastifyReply, FastifyRequest } from "fastify";
import { sendError } from "../lib/errors";
import { getUserByClerkId, upsertUser } from "../services/users";

const clerk = createClerkClient({
  secretKey: process.env.CLERK_SECRET_KEY!,
  publishableKey: process.env.CLERK_PUBLISHABLE_KEY,
});

function toClerkRequest(request: FastifyRequest) {
  const headers = new Headers(
    Object.keys(request.headers).reduce((acc, key) => {
      const value = request.headers[key];
      if (value !== undefined) {
        acc.set(key, Array.isArray(value) ? value.join(",") : value);
      }
      return acc;
    }, new Headers()),
  );
  const url = new URL(request.url, `${request.protocol}://clerk-dummy`);
  return new Request(url, { method: request.method, headers });
}

export async function requireAuth(request: FastifyRequest, reply: FastifyReply) {
  // ---- E2E auth bypass — dev only, never enable in prod ----
  if (process.env.DISABLE_CLERK_AUTH === "1") {
    const testUserId = process.env.E2E_TEST_USER_ID ?? "00000000-0000-0000-0000-000000000001";
    const existing = await getUserByClerkId(`e2e-${testUserId}`);
    const localUser = existing ?? (await upsertUser(`e2e-${testUserId}`, "e2e@test.local", "E2E Test User"));
    request.userId = localUser.id;
    (request as any).auth = { userId: `e2e-${testUserId}` };
    return;
  }
  // ---- end bypass ----

  const req = toClerkRequest(request);
  const state = await clerk.authenticateRequest(req, {
    secretKey: process.env.CLERK_SECRET_KEY,
  });
  if (!state.isSignedIn) {
    return sendError(reply, 401, "Unauthorized", "UNAUTHORIZED");
  }
  const auth = state.toAuth();
  request.auth = auth;

  // Resolve Clerk user to local DB user (UUID) so FK constraints work
  try {
    let localUser = await getUserByClerkId(auth.userId);
    if (!localUser) {
      let email: string | undefined;
      let name: string | undefined;
      try {
        const clerkUser = await clerkClient.users.getUser(auth.userId);
        email = clerkUser.emailAddresses[0]?.emailAddress ?? undefined;
        name = clerkUser.fullName ?? undefined;
      } catch (clerkErr) {
        const err = clerkErr as { status?: number; code?: string };
        const isTransient = err.status === 503 || err.status === 504 || err.code === "timeout";
        if (isTransient) {
          request.log.warn({ err: clerkErr }, "Clerk API transient failure; refusing request");
          return sendError(reply, 503, "Auth service temporarily unavailable", "USER_RESOLUTION_ERROR");
        }
        request.log.error({ err: clerkErr }, "Clerk API user lookup failed; refusing request");
        return sendError(reply, 503, "Failed to resolve user identity", "USER_RESOLUTION_ERROR");
      }
      localUser = await upsertUser(auth.userId, email ?? `${auth.userId}@placeholder.local`, name ?? "User");
    }
    request.userId = localUser.id;
  } catch (err) {
    request.log.error({ err }, "User resolution failed");
    return sendError(reply, 500, "Failed to resolve user", "USER_RESOLUTION_ERROR");
  }
}
