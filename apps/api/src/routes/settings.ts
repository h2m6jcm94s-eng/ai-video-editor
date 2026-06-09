// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { FastifyInstance } from "fastify";
import { eq, and } from "drizzle-orm";
import { db } from "../db";
import { providerKeys } from "../db/schema";
import { providerKeySchema, testProviderKeySchema } from "@ai-video-editor/shared-types";
import { validateBody } from "../middleware/validate";
import { sendError } from "../lib/errors";
import { getUsageForUser } from "../middleware/tokenBudget";

// Simple XOR encryption for demo — replace with AES-256-GCM + KEK in production
function encrypt(key: string, secret: string): string {
  const buf = Buffer.from(key);
  const sec = Buffer.from(secret);
  const out = Buffer.alloc(buf.length);
  for (let i = 0; i < buf.length; i++) {
    out[i] = buf[i] ^ sec[i % sec.length];
  }
  return out.toString("base64");
}

function decrypt(cipher: string, secret: string): string {
  const buf = Buffer.from(cipher, "base64");
  const sec = Buffer.from(secret);
  const out = Buffer.alloc(buf.length);
  for (let i = 0; i < buf.length; i++) {
    out[i] = buf[i] ^ sec[i % sec.length];
  }
  return out.toString("utf-8");
}

const ENCRYPTION_SECRET = process.env.PROVIDER_ENCRYPTION_SECRET || "dev-secret-do-not-use-in-production";

export async function settingsRoutes(app: FastifyInstance) {
  // Get user's AI token usage
  app.get("/usage", async (request) => {
    const userId = request.userId;
    const usage = await getUsageForUser(userId);
    return usage;
  });

  // List user's provider keys (masked)
  app.get("/provider-keys", async (request, reply) => {
    const userId = request.userId;
    const rows = await db.query.providerKeys.findMany({
      where: eq(providerKeys.userId, userId),
    });
    return {
      keys: rows.map((r) => ({
        provider: r.provider,
        masked: maskKey(decrypt(r.encryptedKey, ENCRYPTION_SECRET)),
        createdAt: r.createdAt,
      })),
    };
  });

  // Save/update a provider key
  app.post("/provider-keys", { preHandler: validateBody(providerKeySchema) }, async (request, reply) => {
    const body = request.validatedBody as { provider: string; key: string };
    const userId = request.userId;

    const encrypted = encrypt(body.key, ENCRYPTION_SECRET);

    await db
      .insert(providerKeys)
      .values({ userId, provider: body.provider, encryptedKey: encrypted })
      .onConflictDoUpdate({
        target: [providerKeys.userId, providerKeys.provider],
        set: { encryptedKey: encrypted, updatedAt: new Date() },
      });

    return { success: true };
  });

  // Delete a provider key
  app.delete("/provider-keys/:provider", async (request, reply) => {
    const { provider } = request.params as { provider: string };
    const userId = request.userId;

    await db
      .delete(providerKeys)
      .where(and(eq(providerKeys.userId, userId), eq(providerKeys.provider, provider)));

    return { success: true };
  });

  // Test a provider key (cheap call)
  app.post("/provider-keys/test", { preHandler: validateBody(testProviderKeySchema) }, async (request, reply) => {
    const body = request.validatedBody as { provider: string };
    const userId = request.userId;

    const row = await db.query.providerKeys.findFirst({
      where: and(eq(providerKeys.userId, userId), eq(providerKeys.provider, body.provider)),
    });

    if (!row) {
      return sendError(reply, 404, "Key not found", "NOT_FOUND");
    }

    const key = decrypt(row.encryptedKey, ENCRYPTION_SECRET);

    try {
      if (body.provider === "anthropic") {
        const res = await fetch("https://api.anthropic.com/v1/messages", {
          method: "POST",
          headers: {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            model: "claude-3-haiku-20240307",
            max_tokens: 1,
            messages: [{ role: "user", content: "hi" }],
          }),
        });
        if (!res.ok) throw new Error(await res.text());
      } else if (body.provider === "openai") {
        const res = await fetch("https://api.openai.com/v1/chat/completions", {
          method: "POST",
          headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
          body: JSON.stringify({ model: "gpt-4o-mini", max_tokens: 1, messages: [{ role: "user", content: "hi" }] }),
        });
        if (!res.ok) throw new Error(await res.text());
      } else {
        return sendError(reply, 400, "Unsupported provider", "VALIDATION_ERROR");
      }
      return { success: true };
    } catch (err: unknown) {
      return sendError(reply, 400, err instanceof Error ? err.message : "Test failed", "PROVIDER_INVALID_RESPONSE");
    }
  });
}

function maskKey(key: string): string {
  if (key.length <= 12) return "***";
  return key.slice(0, 6) + "..." + key.slice(-4);
}
