// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.

import {
  providerEncryptedKeySchema,
  providerKeySchema,
  testProviderKeySchema,
} from "@ai-video-editor/shared-types";
import { and, eq } from "drizzle-orm";
import { FastifyInstance } from "fastify";
import { db } from "../db";
import { providerKeys } from "../db/schema";
import { decrypt as aesDecrypt, encrypt as aesEncrypt } from "../lib/crypto";
import { sendError } from "../lib/errors";
import { getUsageForUser } from "../middleware/tokenBudget";
import { validateBody } from "../middleware/validate";

export async function settingsRoutes(app: FastifyInstance) {
  // Get user's AI token usage
  app.get("/usage", async (request) => {
    const userId = request.userId;
    const usage = await getUsageForUser(userId);
    return usage;
  });

  // List user's provider keys (masked)
  app.get("/provider-keys", async (request) => {
    const userId = request.userId;
    const rows = await db.query.providerKeys.findMany({
      where: eq(providerKeys.userId, userId),
    });
    return {
      keys: rows.map((r) => ({
        provider: r.provider,
        masked: maskKey(aesDecrypt(r.encryptedKey)),
        createdAt: r.createdAt,
      })),
    };
  });

  // Save/update a provider key
  app.post("/provider-keys", { preHandler: validateBody(providerKeySchema) }, async (request, reply) => {
    const body = request.validatedBody as { provider: string; key: string };
    const userId = request.userId;

    let encrypted: string;
    try {
      encrypted = providerEncryptedKeySchema.parse(aesEncrypt(body.key));
    } catch (err) {
      return sendError(reply, 422, "Invalid encrypted key format", "VALIDATION_ERROR");
    }

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

    const [deleted] = await db
      .delete(providerKeys)
      .where(and(eq(providerKeys.userId, userId), eq(providerKeys.provider, provider)))
      .returning();

    if (!deleted) {
      return sendError(reply, 404, "Key not found", "NOT_FOUND");
    }

    return { success: true };
  });

  // Test a provider key (cheap call)
  app.post(
    "/provider-keys/test",
    { preHandler: validateBody(testProviderKeySchema) },
    async (request, reply) => {
      const body = request.validatedBody as { provider: string };
      const userId = request.userId;

      const row = await db.query.providerKeys.findFirst({
        where: and(eq(providerKeys.userId, userId), eq(providerKeys.provider, body.provider)),
      });

      if (!row) {
        return sendError(reply, 404, "Key not found", "NOT_FOUND");
      }

      const key = aesDecrypt(row.encryptedKey);

      async function probe(url: string, init: RequestInit) {
        const res = await fetch(url, {
          ...init,
          signal: AbortSignal.timeout(10_000),
        });
        if (!res.ok) {
          throw new Error("Provider rejected the key");
        }
      }

      try {
        if (body.provider === "anthropic") {
          await probe("https://api.anthropic.com/v1/messages", {
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
        } else if (body.provider === "openai") {
          await probe("https://api.openai.com/v1/chat/completions", {
            method: "POST",
            headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
            body: JSON.stringify({
              model: "gpt-4o-mini",
              max_tokens: 1,
              messages: [{ role: "user", content: "hi" }],
            }),
          });
        } else if (body.provider === "kimi") {
          await probe("https://api.moonshot.cn/v1/chat/completions", {
            method: "POST",
            headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
            body: JSON.stringify({
              model: "moonshot-v1-8k",
              max_tokens: 1,
              messages: [{ role: "user", content: "hi" }],
            }),
          });
        } else if (body.provider === "openrouter") {
          await probe("https://openrouter.ai/api/v1/chat/completions", {
            method: "POST",
            headers: {
              Authorization: `Bearer ${key}`,
              "Content-Type": "application/json",
              "HTTP-Referer": process.env.WEB_URL || "http://localhost:3000",
              "X-Title": "AI Video Editor",
            },
            body: JSON.stringify({
              model: "anthropic/claude-3.5-haiku",
              max_tokens: 1,
              messages: [{ role: "user", content: "hi" }],
            }),
          });
        } else if (body.provider === "groq") {
          await probe("https://api.groq.com/openai/v1/chat/completions", {
            method: "POST",
            headers: {
              Authorization: `Bearer ${key}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              model: "llama-3.3-70b-versatile",
              max_tokens: 1,
              messages: [{ role: "user", content: "hi" }],
            }),
          });
        } else {
          return sendError(reply, 400, "Unsupported provider", "VALIDATION_ERROR");
        }
        return { success: true };
      } catch (err: unknown) {
        let message = "Provider test failed";
        if (err instanceof Error) {
          if (err.name === "AbortError" || err.message.toLowerCase().includes("timeout")) {
            message = "Provider test timed out";
          }
        }
        return sendError(reply, 400, message, "PROVIDER_INVALID_RESPONSE");
      }
    },
  );
}

function maskKey(key: string): string {
  if (key.length <= 12) return "***";
  return key.slice(0, 6) + "..." + key.slice(-4);
}
