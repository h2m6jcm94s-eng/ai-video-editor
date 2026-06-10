// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
/**
 * Safe fallback shapes for AI endpoints when the provider refuses,
 * returns invalid JSON, or fails schema validation after retry.
 */

export type AiEndpoint = "describe_project" | "prompt_edit" | "transcribe" | "title_suggest";

export interface SafeFallback<T> {
  data: T;
  refused: true;
  reason: "blocked" | "invalid_json" | "content_filter";
}

interface PromptEditFallbackData {
  diff: unknown[];
  explanation: string;
  newCutList?: unknown;
}

export function safeFallbackFor(
  endpoint: AiEndpoint,
  reason: SafeFallback<unknown>["reason"],
  context: { previousCutList?: unknown }
): SafeFallback<unknown> {
  switch (endpoint) {
    case "describe_project":
      return { data: { description: null }, refused: true, reason };
    case "prompt_edit": {
      const data: PromptEditFallbackData = {
        diff: [],
        explanation:
          reason === "blocked"
            ? "AI declined to respond due to safety policies. No changes applied."
            : reason === "content_filter"
              ? "AI response was blocked by content filters. No changes applied."
              : "AI returned an unexpected response. No changes applied.",
        newCutList: context.previousCutList ?? null,
      };
      return { data, refused: true, reason };
    }
    case "transcribe":
      return { data: { subtitles: [] }, refused: true, reason };
    case "title_suggest":
      return { data: { suggestions: [] }, refused: true, reason };
  }
}
