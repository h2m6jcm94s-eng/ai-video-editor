// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
/**
 * Per-user error event recording.
 *
 * Called from sendError() to persist every 4xx/5xx response per-user.
 * Deduplicates by (userId, code, message hash) within a 5-minute window.
 * Caps unacknowledged events at 50 per user (oldest dropped).
 */

import { and, count, eq, gte, sql } from "drizzle-orm";
import { db } from "../db";
import { userEvents } from "../db/schema";
import { publishNotification } from "../services/queue";

const DEDUP_WINDOW_MINUTES = 5;
const MAX_UNACKED_PER_USER = 50;

function hashEvent(code: string, message: string): string {
  // Simple hash for dedup — good enough for this use case
  let h = 0;
  const str = `${code}:${message}`;
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) - h + str.charCodeAt(i)) | 0;
  }
  return String(h);
}

interface RecordEventInput {
  userId: string;
  code: string;
  message: string;
  details?: unknown;
  route?: string;
}

/**
 * Record a user-facing error event.
 *
 * Deduplicates by (userId, code, message) within 5 minutes.
 * If the user already has 50 unacknowledged events, the oldest is marked dropped.
 */
export async function recordUserEvent(input: RecordEventInput): Promise<void> {
  const { userId, code, message, details, route } = input;

  // Skip UNAUTHORIZED — user can't see it (signed out)
  if (code === "UNAUTHORIZED") {
    return;
  }

  const eventHash = hashEvent(code, message);
  const windowAgo = new Date(Date.now() - DEDUP_WINDOW_MINUTES * 60 * 1000);

  try {
    // Look for an existing matching event within the dedup window
    const existing = await db.query.userEvents.findFirst({
      where: and(
        eq(userEvents.userId, userId),
        eq(userEvents.code, code),
        gte(userEvents.createdAt, windowAgo),
      ),
      orderBy: (events, { desc }) => [desc(events.createdAt)],
    });

    if (existing && hashEvent(existing.code, existing.message) === eventHash) {
      // Increment occurrence count
      await db
        .update(userEvents)
        .set({
          occurrenceCount: sql`${userEvents.occurrenceCount} + 1`,
          updatedAt: new Date(),
        })
        .where(eq(userEvents.id, existing.id));
      return;
    }

    // Check cap before inserting
    const [{ unackedCount }] = await db
      .select({ unackedCount: count() })
      .from(userEvents)
      .where(and(eq(userEvents.userId, userId), eq(userEvents.acknowledged, false)));

    let dropped = false;
    if (unackedCount >= MAX_UNACKED_PER_USER) {
      // Mark oldest unacknowledged as dropped
      const [oldest] = await db
        .select()
        .from(userEvents)
        .where(and(eq(userEvents.userId, userId), eq(userEvents.acknowledged, false)))
        .orderBy(userEvents.createdAt)
        .limit(1);

      if (oldest) {
        await db
          .update(userEvents)
          .set({ dropped: true, updatedAt: new Date() })
          .where(eq(userEvents.id, oldest.id));
      }
      dropped = true;
    }

    // Insert new event
    const [inserted] = await db
      .insert(userEvents)
      .values({
        userId,
        code,
        message,
        details: details ?? null,
        route: route ?? null,
        dropped,
      })
      .returning();

    // Publish to SSE channel so bell updates live
    if (inserted) {
      await publishNotification(userId, {
        id: inserted.id,
        code: inserted.code,
        message: inserted.message,
        occurrenceCount: inserted.occurrenceCount,
        createdAt: inserted.createdAt?.toISOString() ?? new Date().toISOString(),
      });
    }
  } catch (err) {
    // Never throw — event recording must not break the request
    console.error("[recordUserEvent] failed:", err);
  }
}
