// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
/**
 * AI Provider client for synchronous prompt editing.
 * Mirrors the Python provider system but runs in Node.js for low-latency API calls.
 */

import { cutListSchema } from "@ai-video-editor/shared-types";
import { and, eq } from "drizzle-orm";
import { z } from "zod";
import { db } from "../db";
import { providerKeys } from "../db/schema";
import { type SafeFallback, safeFallbackFor } from "../lib/aiFallbacks";
import { decrypt as aesDecrypt } from "../lib/crypto";
import { aiCallDurationSeconds, aiCallsTotal, guardrailsOutputBlocksTotal } from "../lib/metrics";
import { countTokens } from "../lib/tokens";
import { validateAIResponse } from "../middleware/guardrails";

async function getProviderKey(
  userId: string,
  provider: "anthropic" | "openai" | "kimi" | "openrouter" | "groq",
): Promise<string | undefined> {
  const row = await db.query.providerKeys.findFirst({
    where: and(eq(providerKeys.userId, userId), eq(providerKeys.provider, provider)),
  });
  if (row) return aesDecrypt(row.encryptedKey);
  return undefined;
}

export interface PromptEditContext {
  userId: string;
  prompt: string;
  cutList: unknown;
  beatGrid?: unknown;
  assets?: unknown[];
}

export interface PromptEditResult {
  diff: unknown[];
  explanation: string;
  newCutList?: unknown;
  usage?: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
  };
  /** Present when the AI refused or produced unparseable output */
  fallback?: SafeFallback<unknown>;
}

const SYSTEM_PROMPT = `You are an expert video editor AI assistant. The user describes an edit they want to make in natural language. You must analyze their request and return a JSON Patch (RFC 6902) diff that transforms the current cut-list into the desired state.

Rules:
- Only modify what the user explicitly asks for.
- Use JSON Patch operations: "add", "remove", "replace", "move", "copy".
- Paths use slash notation (e.g., "/slots/0/transitionIn").
- For "add" on arrays, use "-/" to append.
- Provide a clear, concise explanation of what changed.
- If the request is ambiguous, make a reasonable best guess and note it.
- Never delete slots unless explicitly asked.
- Duration changes must keep total within the song length.

Return ONLY this JSON structure:
{
  "diff": [...],
  "explanation": "string"
}`;

const promptEditResponseSchema = z
  .object({
    diff: z.array(z.record(z.unknown())),
    explanation: z.string().min(1),
  })
  .strict();

async function fetchWithRetry(url: string, init: RequestInit & { maxRetries?: number }): Promise<Response> {
  const maxRetries = init.maxRetries ?? 3;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const res = await fetch(url, init);
      if (res.ok) return res;

      const retryable = [429, 502, 503, 504];
      if (!retryable.includes(res.status) || attempt === maxRetries) {
        return res;
      }
    } catch (err) {
      if (!(err instanceof TypeError) || attempt === maxRetries) {
        throw err;
      }
    }

    const baseDelay = Math.min(1000 * 2 ** attempt, 8000);
    const jitter = Math.random() * baseDelay;
    await new Promise((r) => setTimeout(r, baseDelay + jitter));
  }

  throw new Error("Fetch retry exhausted");
}

const CAMELCASE_HINT =
  "\nCRITICAL: Your previous JSON was invalid. Return ONLY valid JSON with camelCase keys matching the schema exactly. No markdown fences.";

async function callClaudeOnce(
  context: PromptEditContext,
  hint: string,
): Promise<{ text: string; durationMs: number }> {
  const start = performance.now();
  const anthropicKey =
    (await getProviderKey(context.userId, "anthropic")) || process.env.ANTHROPIC_API_KEY || "";
  if (!anthropicKey) {
    aiCallsTotal.inc({ provider: "claude", status: "missing_key" });
    const err: Error & { code?: string } = new Error("ANTHROPIC_API_KEY not configured");
    err.code = "PROVIDER_KEY_MISSING";
    throw err;
  }

  const res = await fetchWithRetry("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "x-api-key": anthropicKey,
      "anthropic-version": "2023-06-01",
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: "claude-3-5-sonnet-20241022",
      max_tokens: 4096,
      system: SYSTEM_PROMPT + hint,
      messages: [{ role: "user", content: buildPrompt(context) }],
    }),
    signal: AbortSignal.timeout(60_000),
  });

  if (!res.ok) {
    const err = await res.text();
    const status = res.status === 429 ? "rate_limited" : res.status >= 500 ? "server_error" : "client_error";
    aiCallsTotal.inc({ provider: "claude", status });
    aiCallDurationSeconds.observe({ provider: "claude" }, (performance.now() - start) / 1000);
    const error: Error & { code?: string } = new Error(`Claude API error: ${res.status} ${err}`);
    if (res.status === 401 || res.status === 403) error.code = "PROVIDER_INVALID_RESPONSE";
    if (res.status === 429) error.code = "PROVIDER_RATE_LIMITED";
    throw error;
  }

  const data = (await res.json()) as {
    content: Array<{ type: string; text: string }>;
    stop_reason?: string;
  };

  if (data.stop_reason === "refusal") {
    aiCallsTotal.inc({ provider: "claude", status: "refusal" });
    aiCallDurationSeconds.observe({ provider: "claude" }, (performance.now() - start) / 1000);
    return { text: "", durationMs: performance.now() - start };
  }

  const text = data.content?.[0]?.text || "{}";
  aiCallsTotal.inc({ provider: "claude", status: "success" });
  aiCallDurationSeconds.observe({ provider: "claude" }, (performance.now() - start) / 1000);
  return { text, durationMs: performance.now() - start };
}

async function callClaude(context: PromptEditContext): Promise<PromptEditResult> {
  let { text } = await callClaudeOnce(context, "");

  // Refusal → safe fallback
  if (text === "") {
    return {
      diff: [],
      explanation: "AI declined to respond due to safety policies. No changes applied.",
      fallback: safeFallbackFor("prompt_edit", "blocked", { previousCutList: context.cutList }),
    };
  }

  // Output guardrails check
  const guardrailsCheck = await validateAIResponse(text, "claude");
  if (!guardrailsCheck.allowed) {
    const categories = guardrailsCheck.flagged_categories || ["unknown"];
    for (const category of categories) {
      guardrailsOutputBlocksTotal.inc({ category, provider: "claude" });
    }
    return {
      diff: [],
      explanation:
        guardrailsCheck.reason || "AI response was blocked by content filters. No changes applied.",
      fallback: safeFallbackFor("prompt_edit", "content_filter", { previousCutList: context.cutList }),
    };
  }

  let parsed = parseResponse(text);
  if (!parsed) {
    // One retry with explicit camelCase hint
    const retry = await callClaudeOnce(context, CAMELCASE_HINT);
    if (retry.text === "") {
      return {
        diff: [],
        explanation: "AI declined to respond due to safety policies. No changes applied.",
        fallback: safeFallbackFor("prompt_edit", "blocked", { previousCutList: context.cutList }),
      };
    }

    // Output guardrails check on retry
    const retryGuardrailsCheck = await validateAIResponse(retry.text, "claude");
    if (!retryGuardrailsCheck.allowed) {
      const categories = retryGuardrailsCheck.flagged_categories || ["unknown"];
      for (const category of categories) {
        guardrailsOutputBlocksTotal.inc({ category, provider: "claude" });
      }
      return {
        diff: [],
        explanation:
          retryGuardrailsCheck.reason || "AI response was blocked by content filters. No changes applied.",
        fallback: safeFallbackFor("prompt_edit", "content_filter", { previousCutList: context.cutList }),
      };
    }

    parsed = parseResponse(retry.text);
    if (!parsed) {
      return {
        diff: [],
        explanation: "AI returned an unexpected response. No changes applied.",
        fallback: safeFallbackFor("prompt_edit", "invalid_json", { previousCutList: context.cutList }),
      };
    }
    text = retry.text;
  }

  const promptText = buildPrompt(context);
  parsed.usage = {
    promptTokens: await countTokens(promptText),
    completionTokens: await countTokens(text),
    totalTokens: (await countTokens(promptText)) + (await countTokens(text)),
  };
  return parsed;
}

async function callKimiOnce(
  context: PromptEditContext,
  hint: string,
): Promise<{ text: string; durationMs: number }> {
  const start = performance.now();
  const kimiKey =
    (await getProviderKey(context.userId, "kimi")) || process.env.KIMI_API_KEY || process.env.KIMI_KEY || "";
  if (!kimiKey) {
    aiCallsTotal.inc({ provider: "kimi", status: "missing_key" });
    const err: Error & { code?: string } = new Error("KIMI_API_KEY not configured");
    err.code = "PROVIDER_KEY_MISSING";
    throw err;
  }

  const res = await fetchWithRetry("https://api.moonshot.cn/v1/chat/completions", {
    method: "POST",
    headers: {
      authorization: `Bearer ${kimiKey}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: "moonshot-v1-8k",
      messages: [
        { role: "system", content: SYSTEM_PROMPT + hint },
        { role: "user", content: buildPrompt(context) },
      ],
      response_format: { type: "json_object" },
      max_tokens: 4096,
    }),
    signal: AbortSignal.timeout(60_000),
  });

  if (!res.ok) {
    const err = await res.text();
    const status = res.status === 429 ? "rate_limited" : res.status >= 500 ? "server_error" : "client_error";
    aiCallsTotal.inc({ provider: "kimi", status });
    aiCallDurationSeconds.observe({ provider: "kimi" }, (performance.now() - start) / 1000);
    const error: Error & { code?: string } = new Error(`Kimi API error: ${res.status} ${err}`);
    if (res.status === 401 || res.status === 403) error.code = "PROVIDER_INVALID_RESPONSE";
    if (res.status === 429) error.code = "PROVIDER_RATE_LIMITED";
    throw error;
  }

  const data = (await res.json()) as {
    choices: Array<{ message: { content: string }; finish_reason?: string }>;
  };

  if (data.choices?.[0]?.finish_reason === "content_filter") {
    aiCallsTotal.inc({ provider: "kimi", status: "content_filter" });
    aiCallDurationSeconds.observe({ provider: "kimi" }, (performance.now() - start) / 1000);
    return { text: "", durationMs: performance.now() - start };
  }

  const text = data.choices?.[0]?.message?.content || "{}";
  aiCallsTotal.inc({ provider: "kimi", status: "success" });
  aiCallDurationSeconds.observe({ provider: "kimi" }, (performance.now() - start) / 1000);
  return { text, durationMs: performance.now() - start };
}

async function callOpenRouterOnce(
  context: PromptEditContext,
  hint: string,
): Promise<{ text: string; durationMs: number }> {
  const start = performance.now();
  const orKey = (await getProviderKey(context.userId, "openrouter")) || process.env.OPENROUTER_API_KEY || "";
  if (!orKey) {
    aiCallsTotal.inc({ provider: "openrouter", status: "missing_key" });
    const err: Error & { code?: string } = new Error("OPENROUTER_API_KEY not configured");
    err.code = "PROVIDER_KEY_MISSING";
    throw err;
  }

  const res = await fetchWithRetry("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: {
      authorization: `Bearer ${orKey}`,
      "content-type": "application/json",
      "http-referer": process.env.WEB_URL || "http://localhost:3000",
      "x-title": "AI Video Editor",
    },
    body: JSON.stringify({
      model: "anthropic/claude-3.5-haiku",
      messages: [
        { role: "system", content: SYSTEM_PROMPT + hint },
        { role: "user", content: buildPrompt(context) },
      ],
      response_format: { type: "json_object" },
      max_tokens: 4096,
    }),
    signal: AbortSignal.timeout(60_000),
  });

  if (!res.ok) {
    const err = await res.text();
    const status = res.status === 429 ? "rate_limited" : res.status >= 500 ? "server_error" : "client_error";
    aiCallsTotal.inc({ provider: "openrouter", status });
    aiCallDurationSeconds.observe({ provider: "openrouter" }, (performance.now() - start) / 1000);
    const error: Error & { code?: string } = new Error(`OpenRouter API error: ${res.status} ${err}`);
    if (res.status === 401 || res.status === 403) error.code = "PROVIDER_INVALID_RESPONSE";
    if (res.status === 429) error.code = "PROVIDER_RATE_LIMITED";
    throw error;
  }

  const data = (await res.json()) as {
    choices: Array<{ message: { content: string }; finish_reason?: string }>;
  };

  if (data.choices?.[0]?.finish_reason === "content_filter") {
    aiCallsTotal.inc({ provider: "openrouter", status: "content_filter" });
    aiCallDurationSeconds.observe({ provider: "openrouter" }, (performance.now() - start) / 1000);
    return { text: "", durationMs: performance.now() - start };
  }

  const text = data.choices?.[0]?.message?.content || "{}";
  aiCallsTotal.inc({ provider: "openrouter", status: "success" });
  aiCallDurationSeconds.observe({ provider: "openrouter" }, (performance.now() - start) / 1000);
  return { text, durationMs: performance.now() - start };
}

async function callGroqOnce(
  context: PromptEditContext,
  hint: string,
): Promise<{ text: string; durationMs: number }> {
  const start = performance.now();
  const groqKey = (await getProviderKey(context.userId, "groq")) || process.env.GROQ_API_KEY || "";
  if (!groqKey) {
    aiCallsTotal.inc({ provider: "groq", status: "missing_key" });
    const err: Error & { code?: string } = new Error("GROQ_API_KEY not configured");
    err.code = "PROVIDER_KEY_MISSING";
    throw err;
  }

  const res = await fetchWithRetry("https://api.groq.com/openai/v1/chat/completions", {
    method: "POST",
    headers: {
      authorization: `Bearer ${groqKey}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: "llama-3.3-70b-versatile",
      messages: [
        { role: "system", content: SYSTEM_PROMPT + hint },
        { role: "user", content: buildPrompt(context) },
      ],
      response_format: { type: "json_object" },
      max_tokens: 4096,
    }),
    signal: AbortSignal.timeout(60_000),
  });

  if (!res.ok) {
    const err = await res.text();
    const status = res.status === 429 ? "rate_limited" : res.status >= 500 ? "server_error" : "client_error";
    aiCallsTotal.inc({ provider: "groq", status });
    aiCallDurationSeconds.observe({ provider: "groq" }, (performance.now() - start) / 1000);
    const error: Error & { code?: string } = new Error(`Groq API error: ${res.status} ${err}`);
    if (res.status === 401 || res.status === 403) error.code = "PROVIDER_INVALID_RESPONSE";
    if (res.status === 429) error.code = "PROVIDER_RATE_LIMITED";
    throw error;
  }

  const data = (await res.json()) as {
    choices: Array<{ message: { content: string }; finish_reason?: string }>;
  };

  if (data.choices?.[0]?.finish_reason === "content_filter") {
    aiCallsTotal.inc({ provider: "groq", status: "content_filter" });
    aiCallDurationSeconds.observe({ provider: "groq" }, (performance.now() - start) / 1000);
    return { text: "", durationMs: performance.now() - start };
  }

  const text = data.choices?.[0]?.message?.content || "{}";
  aiCallsTotal.inc({ provider: "groq", status: "success" });
  aiCallDurationSeconds.observe({ provider: "groq" }, (performance.now() - start) / 1000);
  return { text, durationMs: performance.now() - start };
}

async function callGroq(context: PromptEditContext): Promise<PromptEditResult> {
  let { text } = await callGroqOnce(context, "");

  if (text === "") {
    return {
      diff: [],
      explanation: "AI response was blocked by content filters. No changes applied.",
      fallback: safeFallbackFor("prompt_edit", "content_filter", { previousCutList: context.cutList }),
    };
  }

  const guardrailsCheck = await validateAIResponse(text, "groq");
  if (!guardrailsCheck.allowed) {
    const categories = guardrailsCheck.flagged_categories || ["unknown"];
    for (const category of categories) {
      guardrailsOutputBlocksTotal.inc({ category, provider: "groq" });
    }
    return {
      diff: [],
      explanation:
        guardrailsCheck.reason || "AI response was blocked by content filters. No changes applied.",
      fallback: safeFallbackFor("prompt_edit", "content_filter", { previousCutList: context.cutList }),
    };
  }

  let parsed = parseResponse(text);
  if (!parsed) {
    const retry = await callGroqOnce(context, CAMELCASE_HINT);
    if (retry.text === "") {
      return {
        diff: [],
        explanation: "AI response was blocked by content filters. No changes applied.",
        fallback: safeFallbackFor("prompt_edit", "content_filter", { previousCutList: context.cutList }),
      };
    }

    const retryGuardrailsCheck = await validateAIResponse(retry.text, "groq");
    if (!retryGuardrailsCheck.allowed) {
      const categories = retryGuardrailsCheck.flagged_categories || ["unknown"];
      for (const category of categories) {
        guardrailsOutputBlocksTotal.inc({ category, provider: "groq" });
      }
      return {
        diff: [],
        explanation:
          retryGuardrailsCheck.reason || "AI response was blocked by content filters. No changes applied.",
        fallback: safeFallbackFor("prompt_edit", "content_filter", { previousCutList: context.cutList }),
      };
    }

    parsed = parseResponse(retry.text);
    if (!parsed) {
      return {
        diff: [],
        explanation: "AI returned an unexpected response. No changes applied.",
        fallback: safeFallbackFor("prompt_edit", "invalid_json", { previousCutList: context.cutList }),
      };
    }
    text = retry.text;
  }

  const promptText = buildPrompt(context);
  parsed.usage = {
    promptTokens: await countTokens(promptText),
    completionTokens: await countTokens(text),
    totalTokens: (await countTokens(promptText)) + (await countTokens(text)),
  };
  return parsed;
}

async function callOpenRouter(context: PromptEditContext): Promise<PromptEditResult> {
  let { text } = await callOpenRouterOnce(context, "");

  if (text === "") {
    return {
      diff: [],
      explanation: "AI response was blocked by content filters. No changes applied.",
      fallback: safeFallbackFor("prompt_edit", "content_filter", { previousCutList: context.cutList }),
    };
  }

  const guardrailsCheck = await validateAIResponse(text, "openrouter");
  if (!guardrailsCheck.allowed) {
    const categories = guardrailsCheck.flagged_categories || ["unknown"];
    for (const category of categories) {
      guardrailsOutputBlocksTotal.inc({ category, provider: "openrouter" });
    }
    return {
      diff: [],
      explanation:
        guardrailsCheck.reason || "AI response was blocked by content filters. No changes applied.",
      fallback: safeFallbackFor("prompt_edit", "content_filter", { previousCutList: context.cutList }),
    };
  }

  let parsed = parseResponse(text);
  if (!parsed) {
    const retry = await callOpenRouterOnce(context, CAMELCASE_HINT);
    if (retry.text === "") {
      return {
        diff: [],
        explanation: "AI response was blocked by content filters. No changes applied.",
        fallback: safeFallbackFor("prompt_edit", "content_filter", { previousCutList: context.cutList }),
      };
    }

    const retryGuardrailsCheck = await validateAIResponse(retry.text, "openrouter");
    if (!retryGuardrailsCheck.allowed) {
      const categories = retryGuardrailsCheck.flagged_categories || ["unknown"];
      for (const category of categories) {
        guardrailsOutputBlocksTotal.inc({ category, provider: "openrouter" });
      }
      return {
        diff: [],
        explanation:
          retryGuardrailsCheck.reason || "AI response was blocked by content filters. No changes applied.",
        fallback: safeFallbackFor("prompt_edit", "content_filter", { previousCutList: context.cutList }),
      };
    }

    parsed = parseResponse(retry.text);
    if (!parsed) {
      return {
        diff: [],
        explanation: "AI returned an unexpected response. No changes applied.",
        fallback: safeFallbackFor("prompt_edit", "invalid_json", { previousCutList: context.cutList }),
      };
    }
    text = retry.text;
  }

  const promptText = buildPrompt(context);
  parsed.usage = {
    promptTokens: await countTokens(promptText),
    completionTokens: await countTokens(text),
    totalTokens: (await countTokens(promptText)) + (await countTokens(text)),
  };
  return parsed;
}

async function callKimi(context: PromptEditContext): Promise<PromptEditResult> {
  let { text } = await callKimiOnce(context, "");

  if (text === "") {
    return {
      diff: [],
      explanation: "AI response was blocked by content filters. No changes applied.",
      fallback: safeFallbackFor("prompt_edit", "content_filter", { previousCutList: context.cutList }),
    };
  }

  const guardrailsCheck = await validateAIResponse(text, "kimi");
  if (!guardrailsCheck.allowed) {
    const categories = guardrailsCheck.flagged_categories || ["unknown"];
    for (const category of categories) {
      guardrailsOutputBlocksTotal.inc({ category, provider: "kimi" });
    }
    return {
      diff: [],
      explanation:
        guardrailsCheck.reason || "AI response was blocked by content filters. No changes applied.",
      fallback: safeFallbackFor("prompt_edit", "content_filter", { previousCutList: context.cutList }),
    };
  }

  let parsed = parseResponse(text);
  if (!parsed) {
    const retry = await callKimiOnce(context, CAMELCASE_HINT);
    if (retry.text === "") {
      return {
        diff: [],
        explanation: "AI response was blocked by content filters. No changes applied.",
        fallback: safeFallbackFor("prompt_edit", "content_filter", { previousCutList: context.cutList }),
      };
    }

    const retryGuardrailsCheck = await validateAIResponse(retry.text, "kimi");
    if (!retryGuardrailsCheck.allowed) {
      const categories = retryGuardrailsCheck.flagged_categories || ["unknown"];
      for (const category of categories) {
        guardrailsOutputBlocksTotal.inc({ category, provider: "kimi" });
      }
      return {
        diff: [],
        explanation:
          retryGuardrailsCheck.reason || "AI response was blocked by content filters. No changes applied.",
        fallback: safeFallbackFor("prompt_edit", "content_filter", { previousCutList: context.cutList }),
      };
    }

    parsed = parseResponse(retry.text);
    if (!parsed) {
      return {
        diff: [],
        explanation: "AI returned an unexpected response. No changes applied.",
        fallback: safeFallbackFor("prompt_edit", "invalid_json", { previousCutList: context.cutList }),
      };
    }
    text = retry.text;
  }

  const promptText = buildPrompt(context);
  parsed.usage = {
    promptTokens: await countTokens(promptText),
    completionTokens: await countTokens(text),
    totalTokens: (await countTokens(promptText)) + (await countTokens(text)),
  };
  return parsed;
}

async function callOpenAIOnce(
  context: PromptEditContext,
  hint: string,
): Promise<{ text: string; durationMs: number }> {
  const start = performance.now();
  const openaiKey = (await getProviderKey(context.userId, "openai")) || process.env.OPENAI_API_KEY || "";
  if (!openaiKey) {
    aiCallsTotal.inc({ provider: "openai", status: "missing_key" });
    const err: Error & { code?: string } = new Error("OPENAI_API_KEY not configured");
    err.code = "PROVIDER_KEY_MISSING";
    throw err;
  }

  const res = await fetchWithRetry("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      authorization: `Bearer ${openaiKey}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: "gpt-4o",
      messages: [
        { role: "system", content: SYSTEM_PROMPT + hint },
        { role: "user", content: buildPrompt(context) },
      ],
      response_format: { type: "json_object" },
      max_tokens: 4096,
    }),
    signal: AbortSignal.timeout(60_000),
  });

  if (!res.ok) {
    const err = await res.text();
    const status = res.status === 429 ? "rate_limited" : res.status >= 500 ? "server_error" : "client_error";
    aiCallsTotal.inc({ provider: "openai", status });
    aiCallDurationSeconds.observe({ provider: "openai" }, (performance.now() - start) / 1000);
    const error: Error & { code?: string } = new Error(`OpenAI API error: ${res.status} ${err}`);
    if (res.status === 401 || res.status === 403) error.code = "PROVIDER_INVALID_RESPONSE";
    if (res.status === 429) error.code = "PROVIDER_RATE_LIMITED";
    throw error;
  }

  const data = (await res.json()) as {
    choices: Array<{ message: { content: string }; finish_reason?: string }>;
  };

  if (data.choices?.[0]?.finish_reason === "content_filter") {
    aiCallsTotal.inc({ provider: "openai", status: "content_filter" });
    aiCallDurationSeconds.observe({ provider: "openai" }, (performance.now() - start) / 1000);
    return { text: "", durationMs: performance.now() - start };
  }

  const text = data.choices?.[0]?.message?.content || "{}";
  aiCallsTotal.inc({ provider: "openai", status: "success" });
  aiCallDurationSeconds.observe({ provider: "openai" }, (performance.now() - start) / 1000);
  return { text, durationMs: performance.now() - start };
}

async function callOpenAI(context: PromptEditContext): Promise<PromptEditResult> {
  let { text } = await callOpenAIOnce(context, "");

  // Content filter → safe fallback
  if (text === "") {
    return {
      diff: [],
      explanation: "AI response was blocked by content filters. No changes applied.",
      fallback: safeFallbackFor("prompt_edit", "content_filter", { previousCutList: context.cutList }),
    };
  }

  // Output guardrails check
  const guardrailsCheck = await validateAIResponse(text, "openai");
  if (!guardrailsCheck.allowed) {
    const categories = guardrailsCheck.flagged_categories || ["unknown"];
    for (const category of categories) {
      guardrailsOutputBlocksTotal.inc({ category, provider: "openai" });
    }
    return {
      diff: [],
      explanation:
        guardrailsCheck.reason || "AI response was blocked by content filters. No changes applied.",
      fallback: safeFallbackFor("prompt_edit", "content_filter", { previousCutList: context.cutList }),
    };
  }

  let parsed = parseResponse(text);
  if (!parsed) {
    // One retry with explicit camelCase hint
    const retry = await callOpenAIOnce(context, CAMELCASE_HINT);
    if (retry.text === "") {
      return {
        diff: [],
        explanation: "AI response was blocked by content filters. No changes applied.",
        fallback: safeFallbackFor("prompt_edit", "content_filter", { previousCutList: context.cutList }),
      };
    }

    // Output guardrails check on retry
    const retryGuardrailsCheck = await validateAIResponse(retry.text, "openai");
    if (!retryGuardrailsCheck.allowed) {
      const categories = retryGuardrailsCheck.flagged_categories || ["unknown"];
      for (const category of categories) {
        guardrailsOutputBlocksTotal.inc({ category, provider: "openai" });
      }
      return {
        diff: [],
        explanation:
          retryGuardrailsCheck.reason || "AI response was blocked by content filters. No changes applied.",
        fallback: safeFallbackFor("prompt_edit", "content_filter", { previousCutList: context.cutList }),
      };
    }

    parsed = parseResponse(retry.text);
    if (!parsed) {
      return {
        diff: [],
        explanation: "AI returned an unexpected response. No changes applied.",
        fallback: safeFallbackFor("prompt_edit", "invalid_json", { previousCutList: context.cutList }),
      };
    }
    text = retry.text;
  }

  const promptText = buildPrompt(context);
  parsed.usage = {
    promptTokens: await countTokens(promptText),
    completionTokens: await countTokens(text),
    totalTokens: (await countTokens(promptText)) + (await countTokens(text)),
  };
  return parsed;
}

function buildPrompt(context: PromptEditContext): string {
  return [
    `# User Request\n${context.prompt}`,
    ``,
    `# Current CutList\n${JSON.stringify(context.cutList, null, 2)}`,
    context.beatGrid ? `# Beat Grid\n${JSON.stringify(context.beatGrid, null, 2)}` : "",
    context.assets && context.assets.length > 0
      ? `# Available Assets\n${JSON.stringify(context.assets, null, 2)}`
      : "",
    ``,
    `Return the JSON Patch diff and explanation.`,
  ]
    .filter(Boolean)
    .join("\n");
}

function parseResponse(text: string): PromptEditResult | null {
  const cleaned = text
    .trim()
    .replace(/^```json\s*/, "")
    .replace(/^```\s*/, "")
    .replace(/\s*```$/, "");

  let parsed: unknown;
  try {
    parsed = JSON.parse(cleaned);
  } catch {
    return null;
  }

  const validated = promptEditResponseSchema.safeParse(parsed);
  if (!validated.success) {
    return null;
  }

  return {
    diff: validated.data.diff,
    explanation: validated.data.explanation,
  };
}

function applyJsonPatch(target: unknown, patch: unknown[]): unknown {
  const obj = JSON.parse(JSON.stringify(target));

  for (const op of patch) {
    if (typeof op !== "object" || op === null) continue;
    const { op: operation, path, value, from } = op as Record<string, unknown>;
    if (typeof path !== "string") continue;

    const keys = path.split("/").filter((k) => k !== "");
    if (operation === "add") {
      setValue(obj, keys, value, true);
    } else if (operation === "remove") {
      removeValue(obj, keys);
    } else if (operation === "replace") {
      setValue(obj, keys, value, false);
    } else if (operation === "move" && typeof from === "string") {
      const fromKeys = from.split("/").filter((k) => k !== "");
      const val = getValue(obj, fromKeys);
      removeValue(obj, fromKeys);
      setValue(obj, keys, val, true);
    } else if (operation === "copy" && typeof from === "string") {
      const fromKeys = from.split("/").filter((k) => k !== "");
      const val = getValue(obj, fromKeys);
      setValue(obj, keys, val, true);
    }
  }

  return obj;
}

function getValue(obj: unknown, keys: string[]): unknown {
  let current: unknown = obj;
  for (const key of keys) {
    if (Array.isArray(current)) {
      current = current[parseInt(key, 10)];
    } else if (current && typeof current === "object") {
      current = (current as Record<string, unknown>)[key];
    } else {
      return undefined;
    }
  }
  return current;
}

function setValue(obj: unknown, keys: string[], value: unknown, add: boolean): void {
  let current: unknown = obj;
  for (let i = 0; i < keys.length - 1; i++) {
    const key = keys[i];
    if (Array.isArray(current)) {
      current = current[parseInt(key, 10)];
    } else if (current && typeof current === "object") {
      current = (current as Record<string, unknown>)[key];
    }
  }
  const lastKey = keys[keys.length - 1];
  if (Array.isArray(current)) {
    if (lastKey === "-" && add) {
      current.push(value);
    } else {
      current[parseInt(lastKey, 10)] = value;
    }
  } else if (current && typeof current === "object") {
    (current as Record<string, unknown>)[lastKey] = value;
  }
}

function removeValue(obj: unknown, keys: string[]): void {
  let current: unknown = obj;
  for (let i = 0; i < keys.length - 1; i++) {
    const key = keys[i];
    if (Array.isArray(current)) {
      current = current[parseInt(key, 10)];
    } else if (current && typeof current === "object") {
      current = (current as Record<string, unknown>)[key];
    }
  }
  const lastKey = keys[keys.length - 1];
  if (Array.isArray(current)) {
    current.splice(parseInt(lastKey, 10), 1);
  } else if (current && typeof current === "object") {
    delete (current as Record<string, unknown>)[lastKey];
  }
}

export async function transcribeAudio(
  userId: string,
  audioBuffer: Buffer,
  filename: string,
): Promise<Array<{ text: string; start: number; end: number }>> {
  const start = performance.now();
  const openaiKey = (await getProviderKey(userId, "openai")) || process.env.OPENAI_API_KEY || "";
  if (!openaiKey) {
    aiCallsTotal.inc({ provider: "openai", status: "missing_key" });
    const err: Error & { code?: string } = new Error("OPENAI_API_KEY not configured");
    err.code = "PROVIDER_KEY_MISSING";
    throw err;
  }

  const formData = new FormData();
  const blob = new Blob([audioBuffer], { type: "audio/mpeg" });
  formData.append("file", blob, filename);
  formData.append("model", "whisper-1");
  formData.append("response_format", "verbose_json");
  formData.append("timestamp_granularities[]", "segment");

  const res = await fetch("https://api.openai.com/v1/audio/transcriptions", {
    method: "POST",
    headers: { authorization: `Bearer ${openaiKey}` },
    body: formData as unknown as string,
    signal: AbortSignal.timeout(120_000),
  });

  if (!res.ok) {
    const err = await res.text();
    const status = res.status === 429 ? "rate_limited" : res.status >= 500 ? "server_error" : "client_error";
    aiCallsTotal.inc({ provider: "openai", status });
    aiCallDurationSeconds.observe({ provider: "openai" }, (performance.now() - start) / 1000);
    const error: Error & { code?: string } = new Error(`Whisper API error: ${res.status} ${err}`);
    if (res.status === 429) error.code = "PROVIDER_RATE_LIMITED";
    throw error;
  }

  const data = (await res.json()) as {
    segments?: Array<{ text: string; start: number; end: number }>;
    text?: string;
  };

  aiCallsTotal.inc({ provider: "openai", status: "success" });
  aiCallDurationSeconds.observe({ provider: "openai" }, (performance.now() - start) / 1000);
  if (data.segments) {
    return data.segments.map((s) => ({ text: s.text.trim(), start: s.start, end: s.end }));
  }
  return [{ text: (data.text || "").trim(), start: 0, end: 0 }];
}

export async function applyPromptEdit(context: PromptEditContext): Promise<
  PromptEditResult & {
    newCutList: unknown;
    usage: { promptTokens: number; completionTokens: number; totalTokens: number };
  }
> {
  const provider =
    process.env.AI_PROVIDER_TOOLCALL?.split(",")[0]?.trim() ||
    process.env.AI_PROVIDER?.split(",")[0]?.trim() ||
    "claude";

  let result: PromptEditResult;

  function isMissingKey(err: unknown): boolean {
    return (
      err !== null &&
      typeof err === "object" &&
      "code" in err &&
      (err as { code?: string }).code === "PROVIDER_KEY_MISSING"
    );
  }

  async function withFallback<T>(primary: () => Promise<T>, fallback: () => Promise<T>): Promise<T> {
    try {
      return await primary();
    } catch (err) {
      if (isMissingKey(err)) throw err;
      return await fallback();
    }
  }

  try {
    if (provider === "kimi") {
      result = await withFallback(
        () => callKimi(context),
        () => callClaude(context),
      );
    } else if (provider === "claude") {
      result = await withFallback(
        () => callClaude(context),
        () => callOpenAI(context),
      );
    } else if (provider === "openai") {
      result = await withFallback(
        () => callOpenAI(context),
        () => callClaude(context),
      );
    } else if (provider === "openrouter") {
      result = await withFallback(
        () => callOpenRouter(context),
        () => callClaude(context),
      );
    } else if (provider === "groq") {
      result = await withFallback(
        () => callGroq(context),
        () => callClaude(context),
      );
    } else {
      result = await withFallback(
        () => callClaude(context),
        () => callOpenAI(context),
      );
    }
  } catch (err) {
    const code =
      err && typeof err === "object" && "code" in err ? (err as { code?: string }).code : undefined;
    const apiErr: Error & { code?: string } = new Error(
      `AI prompt edit failed: ${err instanceof Error ? err.message : "unknown"}`,
    );
    if (code) apiErr.code = code;
    throw apiErr;
  }

  // If the AI returned a fallback (refusal / invalid JSON after retry), preserve the original cut list
  if (result.fallback) {
    const promptText = buildPrompt(context);
    const usage = result.usage || {
      promptTokens: await countTokens(promptText),
      completionTokens: 0,
      totalTokens: await countTokens(promptText),
    };
    return {
      diff: result.diff,
      explanation: result.explanation,
      newCutList: context.cutList,
      usage,
      fallback: result.fallback,
    };
  }

  const newCutList = applyJsonPatch(context.cutList, result.diff);

  const parseResult = cutListSchema.safeParse(newCutList);
  if (!parseResult.success) {
    const err: Error & { code?: string; details?: unknown } = new Error(
      `Generated cut list does not match schema: ${parseResult.error.issues.map((i) => i.message).join(", ")}`,
    );
    err.code = "CUTLIST_SCHEMA_DRIFT";
    err.details = parseResult.error.issues;
    throw err;
  }

  const promptText = buildPrompt(context);
  const usage = result.usage || {
    promptTokens: await countTokens(promptText),
    completionTokens:
      (await countTokens(result.explanation)) + (await countTokens(JSON.stringify(result.diff))),
    totalTokens: 0,
  };
  if (!result.usage) {
    usage.totalTokens = usage.promptTokens + usage.completionTokens;
  }
  return { ...result, newCutList, usage };
}
