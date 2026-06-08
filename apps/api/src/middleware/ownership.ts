// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import type { FastifyRequest, FastifyReply } from "fastify";
import { eq } from "drizzle-orm";
import { db } from "../db";
import { projects } from "../db/schema";

export async function requireProjectOwnership(
  request: FastifyRequest,
  reply: FastifyReply
) {
  const { id } = request.params as { id: string };
  const project = await db.query.projects.findFirst({
    where: eq(projects.id, id),
  });
  if (!project) {
    return reply.status(404).send({ error: "Not found", code: "NOT_FOUND" });
  }
  if (project.userId !== request.userId) {
    return reply.status(403).send({ error: "Forbidden", code: "FORBIDDEN" });
  }
  request.project = project;
}
