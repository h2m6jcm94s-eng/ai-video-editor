// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
/**
 * Middleware to require admin role.
 * Checks Clerk publicMetadata.role === "admin".
 * Every admin action is audit-logged.
 */

import { clerkClient } from "@clerk/fastify";
import type { FastifyReply, FastifyRequest } from "fastify";
import { db } from "../db";
import { adminAudit } from "../db/schema";
import { sendError } from "../lib/errors";

export async function requireAdmin(request: FastifyRequest, reply: FastifyReply): Promise<void> {
  const userId = request.userId;
  if (!userId) {
    await logAdminAttempt(request, "access_denied_no_user");
    return sendError(reply, 401, "Sign in required", "UNAUTHORIZED");
  }

  try {
    // Fetch fresh role from Clerk — don't trust cached session token
    const clerkUserId = request.auth?.userId;
    if (!clerkUserId) {
      await logAdminAttempt(request, "access_denied_no_clerk_user", userId);
      return sendError(reply, 401, "Sign in required", "UNAUTHORIZED");
    }
    const clerkUser = await clerkClient.users.getUser(clerkUserId);
    const role = clerkUser?.publicMetadata?.role as string | undefined;

    if (role !== "admin") {
      await logAdminAttempt(request, "access_denied_not_admin", userId);
      return sendError(reply, 403, "Admin access required", "FORBIDDEN");
    }

    // Log successful admin access
    await logAdminAttempt(request, "admin_access_granted", userId);
  } catch (err) {
    request.log.error({ err }, "Failed to verify admin role");
    await logAdminAttempt(request, "access_denied_verification_error", userId);
    return sendError(reply, 403, "Unable to verify admin status", "FORBIDDEN");
  }
}

async function logAdminAttempt(request: FastifyRequest, action: string, actorId?: string): Promise<void> {
  try {
    await db.insert(adminAudit).values({
      actorId: actorId || "unknown",
      action,
      targetType: "admin_route",
      targetId: request.url,
      metadata: { method: request.method, ip: request.ip },
    });
  } catch (err) {
    // Never throw — audit failure shouldn't break the request
    request.log.error({ err }, "Failed to write admin audit log");
  }
}
