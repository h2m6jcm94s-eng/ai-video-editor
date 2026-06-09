// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
/**
 * Token budget middleware for AI endpoints.
 *
 * Tracks per-user daily token consumption in Redis and enforces limits.
 */

import type { FastifyRequest, FastifyReply } from "fastify";
import { redis } from "../lib/redis";
import { sendError } from "../lib/errors";
import { countTokens } from "../lib/tokens";
import { tokensConsumedTotal, budgetViolationsTotal } from "../lib/metrics";

const DEFAULT_DAILY_TOKEN_LIMIT = parseInt(
  process.env.DEFAULT_DAILY_TOKEN_LIMIT || "100000",
  10
);

function getDailyKey(userId: string): string {
  const today = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
  return `ave:usage:tokens:${userId}:${today}`;
}

function getLimitKey(userId: string): string {
  return `ave:usage:limit:${userId}`;
}

/**
 * Get the daily token limit for a user.
 * Falls back to DEFAULT_DAILY_TOKEN_LIMIT.
 */
export async function getUserTokenLimit(userId: string): Promise<number> {
  const limit = await redis.get(getLimitKey(userId));
  if (limit) return parseInt(limit, 10);
  return DEFAULT_DAILY_TOKEN_LIMIT;
}

/**
 * Get current daily token usage for a user.
 */
export async function getUserTokenUsage(userId: string): Promise<number> {
  const usage = await redis.get(getDailyKey(userId));
  return usage ? parseInt(usage, 10) : 0;
}

/**
 * Increment token usage for a user.
 * Automatically sets TTL to expire at end of day.
 */
export async function incrementTokenUsage(
  userId: string,
  tokens: number,
  provider: string,
  endpoint: string
): Promise<void> {
  if (tokens <= 0) return;

  const key = getDailyKey(userId);
  const pipeline = redis.pipeline();
  pipeline.incrby(key, tokens);

  // Set expiry at end of day if not already set
  const now = new Date();
  const endOfDay = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59, 999);
  const ttlSeconds = Math.ceil((endOfDay.getTime() - now.getTime()) / 1000);
  pipeline.expire(key, ttlSeconds);

  await pipeline.exec();

  // Record metrics
  tokensConsumedTotal.inc({ provider, endpoint }, tokens);
}

/**
 * Fastify preHandler to enforce token budget before AI calls.
 * Estimates prompt tokens and blocks if user would exceed daily limit.
 */
export async function enforceTokenBudget(
  request: FastifyRequest,
  reply: FastifyReply
): Promise<void> {
  const userId = request.userId;
  if (!userId) return; // Should not happen (auth runs first), but be safe

  // Extract prompt text
  const body = request.body as Record<string, unknown> | undefined;
  const prompt =
    typeof body?.prompt === "string"
      ? body.prompt
      : typeof body?.text === "string"
        ? body.text
        : undefined;

  if (!prompt) return; // No prompt to estimate

  const estimatedTokens = (await countTokens(prompt)) + 500; // Prompt + generous completion estimate
  const currentUsage = await getUserTokenUsage(userId);
  const limit = await getUserTokenLimit(userId);

  if (currentUsage + estimatedTokens > limit) {
    budgetViolationsTotal.inc({ user_id: userId });
    request.log.warn(
      { userId, currentUsage, estimatedTokens, limit },
      "Token budget exceeded"
    );
    return sendError(
      reply,
      429,
      `Daily token budget exceeded. Used ${currentUsage.toLocaleString()} of ${limit.toLocaleString()} tokens.`,
      "BUDGET_EXCEEDED",
      { currentUsage, limit, resetAt: getEndOfDayIso() }
    );
  }
}

function getEndOfDayIso(): string {
  const now = new Date();
  const end = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59, 999);
  return end.toISOString();
}

/**
 * Return usage data for the current user.
 */
export async function getUsageForUser(userId: string): Promise<{
  dailyUsage: number;
  dailyLimit: number;
  remaining: number;
  resetAt: string;
}> {
  const dailyUsage = await getUserTokenUsage(userId);
  const dailyLimit = await getUserTokenLimit(userId);
  return {
    dailyUsage,
    dailyLimit,
    remaining: Math.max(0, dailyLimit - dailyUsage),
    resetAt: getEndOfDayIso(),
  };
}
