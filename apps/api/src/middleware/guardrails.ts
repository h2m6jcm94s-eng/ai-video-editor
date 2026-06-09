// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
/**
 * Guardrails middleware for AI endpoint safety.
 *
 * Calls the Guardrails sidecar service to validate prompts before
 * sending them to AI providers. Fails open if the service is unavailable.
 */

import type { FastifyRequest, FastifyReply } from "fastify";
import { sendError } from "../lib/errors";
import { guardrailsBlocksTotal } from "../lib/metrics";

function getGuardrailsConfig() {
  return {
    url: process.env.GUARDRAILS_URL || "http://localhost:8000",
    timeout: parseInt(process.env.GUARDRAILS_TIMEOUT_MS || "3000", 10),
    enabled: process.env.GUARDRAILS_ENABLED !== "false",
  };
}

interface GuardrailsResponse {
  allowed: boolean;
  reason?: string;
  flagged_categories?: string[];
  confidence?: number;
}

/**
 * Evaluate text against guardrails.
 * Returns {allowed: true} if safe or if service is down (fail-open).
 * Returns {allowed: false, reason} if blocked.
 */
export async function evaluateGuardrails(
  text: string,
  context?: string
): Promise<GuardrailsResponse> {
  const config = getGuardrailsConfig();
  if (!config.enabled) {
    return { allowed: true };
  }

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), config.timeout);

    const res = await fetch(`${config.url}/evaluate`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text, context: context || "" }),
      signal: controller.signal,
    });

    clearTimeout(timeout);

    if (!res.ok) {
      // Fail-open: log warning but don't block
      console.warn(`Guardrails service returned ${res.status}, failing open`);
      return { allowed: true };
    }

    const data = (await res.json()) as GuardrailsResponse;
    return data;
  } catch (err) {
    // Fail-open on network errors, timeouts, etc.
    const isTimeout = err instanceof Error && err.name === "AbortError";
    console.warn(
      isTimeout ? "Guardrails evaluation timed out, failing open" : "Guardrails service unreachable, failing open",
      err
    );
    return { allowed: true };
  }
}

/**
 * Fastify preHandler to validate request body for prompt injection.
 * Apply to AI endpoints.
 */
export async function validatePromptGuardrails(
  request: FastifyRequest,
  reply: FastifyReply
): Promise<void> {
  // Extract prompt text from common request shapes
  const body = request.body as Record<string, unknown> | undefined;
  const prompt = extractPromptText(body);

  if (!prompt || typeof prompt !== "string") {
    // No prompt to validate — skip
    return;
  }

  const result = await evaluateGuardrails(prompt, request.url);

  if (!result.allowed) {
    const route = request.routeOptions?.url || request.url;
    const categories = result.flagged_categories || ["unknown"];
    for (const category of categories) {
      guardrailsBlocksTotal.inc({ category, route });
    }
    request.log.warn(
      { flagged: result.flagged_categories, route },
      "Guardrails blocked prompt"
    );
    return sendError(reply, 400, result.reason || "Prompt violates safety policy", "GUARDRAILS_VIOLATION", {
      flagged_categories: result.flagged_categories,
    });
  }
}

/**
 * Extract prompt text from various request body shapes.
 */
function extractPromptText(body: Record<string, unknown> | undefined): string | undefined {
  if (!body) return undefined;

  // Direct prompt field
  if (typeof body.prompt === "string") {
    return body.prompt;
  }

  // Nested prompt (some APIs wrap it)
  if (typeof body.text === "string") {
    return body.text;
  }

  // Messages array (chat completion style)
  if (Array.isArray(body.messages)) {
    const lastUser = [...body.messages]
      .reverse()
      .find((m: any) => m?.role === "user");
    if (lastUser && typeof lastUser.content === "string") {
      return lastUser.content;
    }
  }

  return undefined;
}
