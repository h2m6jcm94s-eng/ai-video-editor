// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
/**
 * Behavior-corpus hardening math (PR-A4).
 *
 * Mirrors the Python helpers in `services/reason-worker/src/reason_worker/behavior_corpus.py`
 * so the API can enforce the weekly contribution cap and anomaly quarantine centrally.
 */

export const WEEKLY_CONTRIBUTION_CAP = 10;
export const ANOMALY_Z_THRESHOLD = 3.0;

const SIGNAL_FEATURE_KEYS = [
  "speech_ratio",
  "avg_speech_segment_duration_s",
  "multi_speaker_ratio",
  "song_present",
  "song_energy_mean",
  "song_tempo_bpm",
  "song_section_count",
  "clip_count",
  "clip_avg_duration_s",
  "motion_density",
  "motion_variance",
  "aesthetic_score_mean",
  "face_screentime_ratio",
  "multi_face_ratio",
  "shot_diversity",
  "reference_present",
];

function numericVector(signals: Record<string, unknown>): number[] {
  return SIGNAL_FEATURE_KEYS.map((key) => {
    const raw = signals[key];
    if (typeof raw === "boolean") return raw ? 1.0 : 0.0;
    if (typeof raw === "number") return raw;
    return 0.0;
  });
}

function euclidean(a: number[], b: number[]): number {
  let sum = 0;
  for (let i = 0; i < a.length; i++) {
    const diff = a[i] - b[i];
    sum += diff * diff;
  }
  return Math.sqrt(sum);
}

function mean(values: number[]): number {
  if (values.length === 0) return 0.0;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

function std(values: number[]): number {
  if (values.length < 2) return 0.0;
  const m = mean(values);
  const variance = values.reduce((acc, v) => acc + (v - m) ** 2, 0) / (values.length - 1);
  return Math.sqrt(variance);
}

function centroid(entries: Array<{ signals: Record<string, unknown> }>): number[] | null {
  if (entries.length === 0) return null;
  const vectors = entries.map((e) => numericVector(e.signals));
  const dim = vectors[0].length;
  return Array.from({ length: dim }, (_, i) => vectors.reduce((acc, v) => acc + v[i], 0) / vectors.length);
}

export function isAnomalousCorpusEntry(
  signals: Record<string, unknown>,
  activeEntries: Array<{ signals: Record<string, unknown> }>,
): boolean {
  if (activeEntries.length < 2) return false;

  const c = centroid(activeEntries);
  if (!c) return false;

  const newVector = numericVector(signals);
  const distances = activeEntries.map((e) => euclidean(numericVector(e.signals), c));
  const newDistance = euclidean(newVector, c);

  const meanDistance = mean(distances);
  const stdDistance = std(distances);
  if (stdDistance === 0) return newDistance > meanDistance;

  const z = (newDistance - meanDistance) / stdDistance;
  return Math.abs(z) > ANOMALY_Z_THRESHOLD;
}

export function canUserContribute(entriesLast7d: unknown[]): boolean {
  return entriesLast7d.length < WEEKLY_CONTRIBUTION_CAP;
}
