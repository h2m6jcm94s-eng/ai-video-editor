// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { db } from "../db";
import { users } from "../db/schema";
import { eq } from "drizzle-orm";

export async function upsertUser(clerkId: string, email: string, name: string) {
  const [user] = await db
    .insert(users)
    .values({ clerkId, email, name })
    .onConflictDoUpdate({
      target: users.clerkId,
      set: { name, email },
    })
    .returning();
  return user;
}

export async function getUserByClerkId(clerkId: string) {
  return db.query.users.findFirst({
    where: eq(users.clerkId, clerkId),
  });
}
