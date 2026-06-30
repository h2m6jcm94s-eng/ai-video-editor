// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import { eq } from "drizzle-orm";
import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { db } from "../db";
import { userTasteProfiles } from "../db/schema";
import { sendError } from "../lib/errors";
import { validateBody } from "../middleware/validate";

const clusterBiasVectorSchema = z.record(z.record(z.number()));

const patchTasteProfileSchema = z
  .object({
    contributeToGlobalCorpus: z.boolean().optional(),
    clusterBiasVectors: clusterBiasVectorSchema.optional(),
  })
  .strict();

export async function tasteRoutes(app: FastifyInstance) {
  app.get("/", async (request, reply) => {
    const userId = request.userId;
    if (!userId) {
      return sendError(reply, 401, "Unauthorized", "UNAUTHORIZED");
    }

    let profile = await db.query.userTasteProfiles.findFirst({
      where: eq(userTasteProfiles.userId, userId),
    });
    if (!profile) {
      const [created] = await db.insert(userTasteProfiles).values({ userId }).returning();
      profile = created;
    }

    return { profile };
  });

  app.patch("/", { preHandler: validateBody(patchTasteProfileSchema) }, async (request, reply) => {
    const userId = request.userId;
    if (!userId) {
      return sendError(reply, 401, "Unauthorized", "UNAUTHORIZED");
    }

    const body = request.validatedBody as z.infer<typeof patchTasteProfileSchema>;

    const existing = await db.query.userTasteProfiles.findFirst({
      where: eq(userTasteProfiles.userId, userId),
    });

    if (!existing) {
      const [created] = await db
        .insert(userTasteProfiles)
        .values({
          userId,
          contributeToGlobalCorpus: body.contributeToGlobalCorpus,
          clusterBiasVectors: body.clusterBiasVectors,
        })
        .returning();
      return { profile: created };
    }

    const update: Record<string, unknown> = { lastUpdatedAt: new Date() };
    if (body.contributeToGlobalCorpus !== undefined) {
      update.contributeToGlobalCorpus = body.contributeToGlobalCorpus;
    }
    if (body.clusterBiasVectors !== undefined) {
      update.clusterBiasVectors = body.clusterBiasVectors;
    }

    const [updated] = await db
      .update(userTasteProfiles)
      .set(update)
      .where(eq(userTasteProfiles.id, existing.id))
      .returning();

    return { profile: updated };
  });
}
