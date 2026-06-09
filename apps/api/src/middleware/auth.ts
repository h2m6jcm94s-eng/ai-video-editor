// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { createClerkClient, clerkClient } from "@clerk/fastify";
import type { FastifyRequest, FastifyReply } from "fastify";
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
    }, new Headers())
  );
  const url = new URL(request.url, `${request.protocol}://clerk-dummy`);
  return new Request(url, { method: request.method, headers });
}

export async function requireAuth(
  request: FastifyRequest,
  reply: FastifyReply
) {
  const req = toClerkRequest(request);
  const state = await clerk.authenticateRequest(req, {
    secretKey: process.env.CLERK_SECRET_KEY,
  });
  if (!state.isSignedIn) {
    return reply.status(401).send({ error: "Unauthorized", code: "UNAUTHORIZED" });
  }
  const auth = state.toAuth();
  request.auth = auth;

  // Resolve Clerk user to local DB user (UUID) so FK constraints work
  try {
    let localUser = await getUserByClerkId(auth.userId);
    if (!localUser) {
      let email = `${auth.userId}@placeholder.local`;
      let name = "User";
      try {
        const clerkUser = await clerkClient.users.getUser(auth.userId);
        email = clerkUser.emailAddresses[0]?.emailAddress ?? email;
        name = clerkUser.fullName ?? name;
      } catch (clerkErr) {
        request.log.warn({ err: clerkErr }, "Clerk API user lookup failed (using placeholder)");
      }
      localUser = await upsertUser(auth.userId, email, name);
    }
    request.userId = localUser.id;
  } catch (err) {
    request.log.error({ err }, "User resolution failed");
    return reply.status(500).send({ error: "Failed to resolve user", code: "USER_RESOLUTION_ERROR" });
  }
}
