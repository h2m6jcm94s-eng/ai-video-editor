// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
/**
 * AI Provider client for synchronous prompt editing.
 * Mirrors the Python provider system but runs in Node.js for low-latency API calls.
 */

import { eq, and } from "drizzle-orm";
import { db } from "../db";
import { providerKeys } from "../db/schema";
import { aiCallsTotal, aiCallDurationSeconds } from "../lib/metrics";
import { countTokens } from "../lib/tokens";

const ENCRYPTION_SECRET = process.env.PROVIDER_ENCRYPTION_SECRET || "dev-secret-do-not-use-in-production";

// Simple XOR for demo — production should use AES-256-GCM + KEK
function decrypt(cipher: string, secret: string): string {
  const buf = Buffer.from(cipher, "base64");
  const sec = Buffer.from(secret);
  const out = Buffer.alloc(buf.length);
  for (let i = 0; i < buf.length; i++) {
    out[i] = buf[i] ^ sec[i % sec.length];
  }
  return out.toString("utf-8");
}

async function getProviderKey(userId: string, provider: "anthropic" | "openai"): Promise<string | undefined> {
  const row = await db.query.providerKeys.findFirst({
    where: and(eq(providerKeys.userId, userId), eq(providerKeys.provider, provider)),
  });
  if (row) return decrypt(row.encryptedKey, ENCRYPTION_SECRET);
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

async function callClaude(context: PromptEditContext): Promise<PromptEditResult> {
  const start = performance.now();
  const anthropicKey = (await getProviderKey(context.userId, "anthropic")) || process.env.ANTHROPIC_API_KEY || "";
  if (!anthropicKey) {
    aiCallsTotal.inc({ provider: "claude", status: "missing_key" });
    const err: Error & { code?: string } = new Error("ANTHROPIC_API_KEY not configured");
    err.code = "PROVIDER_KEY_MISSING";
    throw err;
  }

  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "x-api-key": anthropicKey,
      "anthropic-version": "2023-06-01",
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: "claude-3-5-sonnet-20241022",
      max_tokens: 4096,
      system: SYSTEM_PROMPT,
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

  const data = (await res.json()) as { content: Array<{ type: string; text: string }> };
  const text = data.content?.[0]?.text || "{}";
  aiCallsTotal.inc({ provider: "claude", status: "success" });
  aiCallDurationSeconds.observe({ provider: "claude" }, (performance.now() - start) / 1000);
  const result = parseResponse(text);
  const promptText = buildPrompt(context);
  result.usage = {
    promptTokens: await countTokens(promptText),
    completionTokens: await countTokens(text),
    totalTokens: await countTokens(promptText) + await countTokens(text),
  };
  return result;
}

async function callOpenAI(context: PromptEditContext): Promise<PromptEditResult> {
  const start = performance.now();
  const openaiKey = (await getProviderKey(context.userId, "openai")) || process.env.OPENAI_API_KEY || "";
  if (!openaiKey) {
    aiCallsTotal.inc({ provider: "openai", status: "missing_key" });
    const err: Error & { code?: string } = new Error("OPENAI_API_KEY not configured");
    err.code = "PROVIDER_KEY_MISSING";
    throw err;
  }

  const res = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      authorization: `Bearer ${openaiKey}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: "gpt-4o",
      messages: [
        { role: "system", content: SYSTEM_PROMPT },
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

  const data = (await res.json()) as { choices: Array<{ message: { content: string } }> };
  const text = data.choices?.[0]?.message?.content || "{}";
  aiCallsTotal.inc({ provider: "openai", status: "success" });
  aiCallDurationSeconds.observe({ provider: "openai" }, (performance.now() - start) / 1000);
  const result = parseResponse(text);
  const promptText = buildPrompt(context);
  result.usage = {
    promptTokens: await countTokens(promptText),
    completionTokens: await countTokens(text),
    totalTokens: await countTokens(promptText) + await countTokens(text),
  };
  return result;
}

function buildPrompt(context: PromptEditContext): string {
  return [
    `# User Request\n${context.prompt}`,
    ``,
    `# Current CutList\n${JSON.stringify(context.cutList, null, 2)}`,
    context.beatGrid ? `# Beat Grid\n${JSON.stringify(context.beatGrid, null, 2)}` : "",
    context.assets && context.assets.length > 0 ? `# Available Assets\n${JSON.stringify(context.assets, null, 2)}` : "",
    ``,
    `Return the JSON Patch diff and explanation.`,
  ]
    .filter(Boolean)
    .join("\n");
}

function parseResponse(text: string): PromptEditResult {
  const cleaned = text
    .trim()
    .replace(/^```json\s*/, "")
    .replace(/^```\s*/, "")
    .replace(/\s*```$/, "");

  try {
    const parsed = JSON.parse(cleaned) as Partial<PromptEditResult>;
    return {
      diff: Array.isArray(parsed.diff) ? parsed.diff : [],
      explanation: typeof parsed.explanation === "string" ? parsed.explanation : "No explanation provided",
    };
  } catch {
    return { diff: [], explanation: text.slice(0, 500) };
  }
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
  filename: string
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

  const data = (await res.json()) as { segments?: Array<{ text: string; start: number; end: number }>; text?: string };

  aiCallsTotal.inc({ provider: "openai", status: "success" });
  aiCallDurationSeconds.observe({ provider: "openai" }, (performance.now() - start) / 1000);
  if (data.segments) {
    return data.segments.map((s) => ({ text: s.text.trim(), start: s.start, end: s.end }));
  }
  return [{ text: (data.text || "").trim(), start: 0, end: 0 }];
}

export async function applyPromptEdit(
  context: PromptEditContext
): Promise<PromptEditResult & { newCutList: unknown; usage: { promptTokens: number; completionTokens: number; totalTokens: number } }> {
  const provider = process.env.AI_PROVIDER?.split(",")[0]?.trim() || "claude";

  let result: PromptEditResult;

  function isMissingKey(err: unknown): boolean {
    return err !== null && typeof err === "object" && "code" in err && (err as { code?: string }).code === "PROVIDER_KEY_MISSING";
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
    if (provider === "claude") {
      result = await withFallback(() => callClaude(context), () => callOpenAI(context));
    } else if (provider === "openai") {
      result = await withFallback(() => callOpenAI(context), () => callClaude(context));
    } else {
      result = await withFallback(() => callClaude(context), () => callOpenAI(context));
    }
  } catch (err) {
    const code = err && typeof err === "object" && "code" in err ? (err as { code?: string }).code : undefined;
    const apiErr: Error & { code?: string } = new Error(
      `AI prompt edit failed: ${err instanceof Error ? err.message : "unknown"}`
    );
    if (code) apiErr.code = code;
    throw apiErr;
  }

  const newCutList = applyJsonPatch(context.cutList, result.diff);
  const promptText = buildPrompt(context);
  const usage = result.usage || {
    promptTokens: await countTokens(promptText),
    completionTokens: await countTokens(result.explanation) + await countTokens(JSON.stringify(result.diff)),
    totalTokens: 0,
  };
  if (!result.usage) {
    usage.totalTokens = usage.promptTokens + usage.completionTokens;
  }
  return { ...result, newCutList, usage };
}
