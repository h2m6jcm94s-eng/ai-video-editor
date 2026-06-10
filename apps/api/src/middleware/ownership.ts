// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import type { FastifyRequest, FastifyReply } from "fastify";
import { eq } from "drizzle-orm";
import { db } from "../db";
import { projects } from "../db/schema";
import { sendError } from "../lib/errors";

export async function requireProjectOwnership(
  request: FastifyRequest,
  reply: FastifyReply
) {
  const { id } = request.params as { id: string };
  const project = await db.query.projects.findFirst({
    where: eq(projects.id, id),
  });
  if (!project) {
    return sendError(reply, 404, "Not found", "NOT_FOUND");
  }
  if (project.userId !== request.userId) {
    return sendError(reply, 403, "Forbidden", "FORBIDDEN");
  }
  request.project = project;
}
