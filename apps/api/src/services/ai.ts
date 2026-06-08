// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
/**
 * AI Provider client for synchronous prompt editing.
 * Mirrors the Python provider system but runs in Node.js for low-latency API calls.
 */

import { env } from "../env";

export interface PromptEditContext {
  prompt: string;
  cutList: unknown;
  beatGrid?: unknown;
  assets?: unknown[];
}

export interface PromptEditResult {
  diff: unknown[];
  explanation: string;
  newCutList?: unknown;
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
  const anthropicKey = process.env.ANTHROPIC_API_KEY || "";
  if (!anthropicKey) {
    throw new Error("ANTHROPIC_API_KEY not configured");
  }

  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "x-api-key": anthropicKey,
      "anthropic-version": "2023-06-01",
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: "claude-sonnet-4-6-20251001",
      max_tokens: 4096,
      system: SYSTEM_PROMPT,
      messages: [
        {
          role: "user",
          content: buildPrompt(context),
        },
      ],
    }),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Claude API error: ${res.status} ${err}`);
  }

  const data = (await res.json()) as {
    content: Array<{ type: string; text: string }>;
  };
  const text = data.content?.[0]?.text || "{}";
  return parseResponse(text);
}

async function callOpenAI(context: PromptEditContext): Promise<PromptEditResult> {
  const openaiKey = process.env.OPENAI_API_KEY || "";
  if (!openaiKey) {
    throw new Error("OPENAI_API_KEY not configured");
  }

  const res = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      authorization: `Bearer ${openaiKey}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: "gpt-4.1",
      messages: [
        { role: "system", content: SYSTEM_PROMPT },
        { role: "user", content: buildPrompt(context) },
      ],
      response_format: { type: "json_object" },
      max_tokens: 4096,
    }),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`OpenAI API error: ${res.status} ${err}`);
  }

  const data = (await res.json()) as {
    choices: Array<{ message: { content: string } }>;
  };
  const text = data.choices?.[0]?.message?.content || "{}";
  return parseResponse(text);
}

function buildPrompt(context: PromptEditContext): string {
  return [
    `# User Request\n${context.prompt}`,
    ``,
    `# Current CutList\n${JSON.stringify(context.cutList, null, 2)}`,
    context.beatGrid
      ? `# Beat Grid\n${JSON.stringify(context.beatGrid, null, 2)}`
      : "",
    context.assets && context.assets.length > 0
      ? `# Available Assets\n${JSON.stringify(context.assets, null, 2)}`
      : "",
    ``,
    `Return the JSON Patch diff and explanation.`,
  ]
    .filter(Boolean)
    .join("\n");
}

function parseResponse(text: string): PromptEditResult {
  // Strip markdown fences
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
    // If JSON parse fails, return empty diff with raw text as explanation
    return { diff: [], explanation: text.slice(0, 500) };
  }
}

function applyJsonPatch(target: unknown, patch: unknown[]): unknown {
  // Deep clone
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

/**
 * Transcribe audio using OpenAI Whisper API.
 * Returns subtitle segments with timing.
 */
export async function transcribeAudio(audioBuffer: Buffer, filename: string): Promise<Array<{ text: string; start: number; end: number }>> {
  const openaiKey = process.env.OPENAI_API_KEY || "";
  if (!openaiKey) {
    throw new Error("OPENAI_API_KEY not configured");
  }

  const formData = new FormData();
  const blob = new Blob([audioBuffer], { type: "audio/mpeg" });
  formData.append("file", blob, filename);
  formData.append("model", "whisper-1");
  formData.append("response_format", "verbose_json");
  formData.append("timestamp_granularities[]", "segment");

  const res = await fetch("https://api.openai.com/v1/audio/transcriptions", {
    method: "POST",
    headers: {
      authorization: `Bearer ${openaiKey}`,
    },
    body: formData as any,
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Whisper API error: ${res.status} ${err}`);
  }

  const data = (await res.json()) as {
    segments?: Array<{ text: string; start: number; end: number }>;
    text?: string;
  };

  if (data.segments) {
    return data.segments.map((s) => ({
      text: s.text.trim(),
      start: s.start,
      end: s.end,
    }));
  }

  // Fallback: return single segment if no segments array
  return [{ text: (data.text || "").trim(), start: 0, end: 0 }];
}

export async function applyPromptEdit(
  context: PromptEditContext
): Promise<PromptEditResult & { newCutList: unknown }> {
  const provider = process.env.AI_PROVIDER?.split(",")[0]?.trim() || "claude";

  let result: PromptEditResult;

  try {
    if (provider === "claude") {
      try {
        result = await callClaude(context);
      } catch {
        result = await callOpenAI(context);
      }
    } else if (provider === "openai") {
      try {
        result = await callOpenAI(context);
      } catch {
        result = await callClaude(context);
      }
    } else {
      // Fallback chain for unknown providers
      try {
        result = await callClaude(context);
      } catch {
        result = await callOpenAI(context);
      }
    }
  } catch (err) {
    throw new Error(
      `AI prompt edit failed: ${err instanceof Error ? err.message : "unknown"}`
    );
  }

  const newCutList = applyJsonPatch(context.cutList, result.diff);
  return { ...result, newCutList };
}
