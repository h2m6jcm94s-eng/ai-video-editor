// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { FastifyInstance } from "fastify";
import { z } from "zod";
import { sendError } from "../lib/errors";

const presenceSchema = z
  .object({
    x: z.number().int(),
    y: z.number().int(),
    name: z.string().max(100).optional(),
  })
  .strict();

interface CursorData {
  x: number;
  y: number;
  userId: string;
  name: string;
  color: string;
  lastSeen: number;
}

const PRESENCE_TTL_MS = 15000;
const presenceStore = new Map<string, Map<string, CursorData>>();

function cleanupPresence(projectId: string) {
  const projectMap = presenceStore.get(projectId);
  if (!projectMap) return;
  const now = Date.now();
  for (const [userId, data] of projectMap) {
    if (now - data.lastSeen > PRESENCE_TTL_MS) {
      projectMap.delete(userId);
    }
  }
  if (projectMap.size === 0) {
    presenceStore.delete(projectId);
  }
}

const COLORS = ["#ef4444", "#f97316", "#eab308", "#22c55e", "#06b6d4", "#3b82f6", "#a855f7", "#ec4899"];

function hashColor(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  return COLORS[Math.abs(hash) % COLORS.length];
}

export async function presenceRoutes(app: FastifyInstance) {
  // Report presence
  app.post(
    "/:id/presence",
    {
      config: {
        rateLimit: {
          max: 60,
          timeWindow: "1 minute",
        },
      },
    },
    async (request, reply) => {
      const { id } = request.params as { id: string };
      const userId = request.userId;

      const parsed = presenceSchema.safeParse(request.body);
      if (!parsed.success) {
        return sendError(reply, 422, "Validation failed", "VALIDATION_ERROR", parsed.error.issues);
      }
      const body = parsed.data;

      let projectMap = presenceStore.get(id);
      if (!projectMap) {
        projectMap = new Map();
        presenceStore.set(id, projectMap);
      }

      projectMap.set(userId, {
        x: body.x,
        y: body.y,
        userId,
        name: body.name || "User",
        color: hashColor(userId),
        lastSeen: Date.now(),
      });

      return { success: true };
    },
  );

  // Get presence for project
  app.get("/:id/presence", async (request, reply) => {
    const { id } = request.params as { id: string };
    const userId = request.userId;
    cleanupPresence(id);

    const projectMap = presenceStore.get(id);
    if (!projectMap) {
      return { users: [] };
    }

    const users = Array.from(projectMap.values())
      .filter((u) => u.userId !== userId)
      .map((u) => ({
        userId: u.userId,
        name: u.name,
        color: u.color,
        x: u.x,
        y: u.y,
      }));

    return { users };
  });
}
