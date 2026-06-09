// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
/**
 * Token counting utilities using tiktoken (dynamic import for ESM compatibility).
 */

let encoding: any = null;

async function getEncoding(): Promise<any> {
  if (encoding) return encoding;
  const { getEncoding: getEnc } = await import("js-tiktoken");
  encoding = getEnc("cl100k_base"); // Used by GPT-4, GPT-3.5, Claude
  return encoding;
}

/**
 * Count tokens in a string.
 */
export async function countTokens(text: string): Promise<number> {
  if (!text) return 0;
  const enc = await getEncoding();
  return enc.encode(text).length;
}

/**
 * Estimate tokens for a prompt + system message context.
 * Rough heuristic: prompt tokens + ~200 tokens for system/context overhead.
 */
export async function estimatePromptTokens(prompt: string, systemContext?: string): Promise<number> {
  const enc = await getEncoding();
  const promptTokens = enc.encode(prompt).length;
  const contextTokens = systemContext ? enc.encode(systemContext).length : 0;
  return promptTokens + contextTokens + 10; // Formatting overhead
}

/**
 * Heuristic: estimate completion tokens from response text.
 */
export async function estimateCompletionTokens(responseText: string): Promise<number> {
  return countTokens(responseText);
}
