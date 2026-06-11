// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
/**
 * Prometheus metrics registry and custom metrics for the API.
 *
 * Provides:
 * - HTTP request counter + duration histogram (via app.ts onResponse hook)
 * - Render lifecycle metrics
 * - AI provider call metrics
 * - Cache hit/miss counter
 * - Queue depth gauge
 * - Error counter
 * - Rate limit hit counter
 */

import { Counter, Gauge, Histogram, register } from "prom-client";

function getOrCreateCounter<T extends string>(opts: { name: string; help: string; labelNames?: T[] }) {
  const existing = register.getSingleMetric(opts.name) as Counter<T> | undefined;
  if (existing) return existing;
  return new Counter({
    name: opts.name,
    help: opts.help,
    labelNames: opts.labelNames as T[],
    registers: [register],
  });
}

function getOrCreateHistogram<T extends string>(opts: {
  name: string;
  help: string;
  labelNames?: T[];
  buckets?: number[];
}) {
  const existing = register.getSingleMetric(opts.name) as Histogram<T> | undefined;
  if (existing) return existing;
  return new Histogram({
    name: opts.name,
    help: opts.help,
    labelNames: opts.labelNames as T[],
    buckets: opts.buckets,
    registers: [register],
  });
}

function getOrCreateGauge(opts: { name: string; help: string }) {
  const existing = register.getSingleMetric(opts.name) as Gauge | undefined;
  if (existing) return existing;
  return new Gauge({
    name: opts.name,
    help: opts.help,
    registers: [register],
  });
}

// ─── HTTP Metrics ───────────────────────────────────────────────────────────

export const httpRequestsTotal = getOrCreateCounter({
  name: "ave_http_requests_total",
  help: "Total HTTP requests",
  labelNames: ["method", "route", "status_code"],
});

export const httpRequestDurationSeconds = getOrCreateHistogram({
  name: "ave_http_request_duration_seconds",
  help: "HTTP request duration in seconds",
  labelNames: ["method", "route"],
  buckets: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
});

// ─── Render Metrics ─────────────────────────────────────────────────────────

export const rendersActive = getOrCreateGauge({
  name: "ave_renders_active",
  help: "Number of renders currently queued or running",
});

export const rendersTotal = getOrCreateCounter({
  name: "ave_renders_total",
  help: "Total renders by outcome",
  labelNames: ["status"],
});

// ─── AI Provider Metrics ────────────────────────────────────────────────────

export const aiCallsTotal = getOrCreateCounter({
  name: "ave_ai_calls_total",
  help: "Total AI provider API calls",
  labelNames: ["provider", "status"],
});

export const aiCallDurationSeconds = getOrCreateHistogram({
  name: "ave_ai_call_duration_seconds",
  help: "AI provider API call duration in seconds",
  labelNames: ["provider"],
  buckets: [0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30, 60],
});

// ─── Cache Metrics ──────────────────────────────────────────────────────────

export const cacheOperationsTotal = getOrCreateCounter({
  name: "ave_cache_operations_total",
  help: "Total cache operations by type and result",
  labelNames: ["operation", "result"],
});

// ─── Queue Metrics ──────────────────────────────────────────────────────────

export const queueDepth = getOrCreateGauge({
  name: "ave_queue_depth",
  help: "Current depth of the job queue",
});

// ─── Error Metrics ──────────────────────────────────────────────────────────

export const errorsTotal = getOrCreateCounter({
  name: "ave_errors_total",
  help: "Total errors by code and route",
  labelNames: ["code", "route"],
});

// ─── Rate Limit Metrics ─────────────────────────────────────────────────────

export const rateLimitHitsTotal = getOrCreateCounter({
  name: "ave_rate_limit_hits_total",
  help: "Total rate limit hits by route",
  labelNames: ["route"],
});

// ─── Guardrails Metrics ─────────────────────────────────────────────────────

export const guardrailsBlocksTotal = getOrCreateCounter({
  name: "ave_guardrails_blocks_total",
  help: "Total guardrails blocks by category and route",
  labelNames: ["category", "route"],
});

export const guardrailsOutputBlocksTotal = getOrCreateCounter({
  name: "ave_guardrails_output_blocks_total",
  help: "Output blocked by guardrails",
  labelNames: ["category", "provider"],
});

// ─── Token Budget Metrics ───────────────────────────────────────────────────

export const tokensConsumedTotal = getOrCreateCounter({
  name: "ave_tokens_consumed_total",
  help: "Total tokens consumed by provider and endpoint",
  labelNames: ["provider", "endpoint"],
});

export const budgetViolationsTotal = getOrCreateCounter({
  name: "ave_budget_violations_total",
  help: "Total budget violations by user",
  labelNames: ["user_id"],
});

// ─── Anomaly Metrics ────────────────────────────────────────────────────────

export const anomaliesDetectedTotal = getOrCreateCounter({
  name: "ave_anomalies_detected_total",
  help: "Total anomalies detected by metric type",
  labelNames: ["metric"],
});

export const slidingWindowRejectsTotal = getOrCreateCounter({
  name: "ave_sliding_window_rejects_total",
  help: "Total requests rejected by sliding window rate limiter",
  labelNames: ["route"],
});

// ─── Startup / Health ───────────────────────────────────────────────────────

export const startupTimestamp = getOrCreateGauge({
  name: "ave_startup_timestamp_seconds",
  help: "Unix timestamp of the last application startup",
});

// Set startup timestamp immediately
startupTimestamp.set(Date.now() / 1000);

// ─── Helpers ────────────────────────────────────────────────────────────────

/**
 * Get Prometheus metrics in exposition format.
 */
export async function getMetrics(): Promise<string> {
  return register.metrics();
}

/**
 * Normalize a route path for metric labels.
 * Replaces UUIDs and numeric IDs with :id placeholders.
 */
export function normalizeRoutePath(path: string): string {
  return path
    .replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, ":id")
    .replace(/\/\d+/g, "/:id");
}
