export interface WedgeMetrics {
  cutCountParity: number;
  pacingCorrelation: number;
  effectCountParity: number;
  shotLengthKL: number;
}

export interface WedgeResult {
  metrics: WedgeMetrics;
  verdict: "PROVEN" | "NOT_PROVEN";
  passCount: number;
}

/* ── Helpers ─────────────────────────────────────────────────────────── */

function getSlots(cutList: unknown): Array<Record<string, unknown>> {
  return ((cutList as Record<string, unknown> | null)?.slots as Array<Record<string, unknown>>) || [];
}

function getDuration(cutList: unknown): number {
  const globals = ((cutList as Record<string, unknown> | null)?.globals as Record<string, unknown>) || {};
  return (globals.totalDurationS as number) || 60;
}

/** Count total effects across all slots */
function countEffects(slots: Array<Record<string, unknown>>): number {
  return slots.reduce((sum, s) => {
    const fx = s.effects as unknown[] | undefined;
    return sum + (fx?.length || 0);
  }, 0);
}

/** Build a 10-bucket pacing histogram (cuts per bucket) */
function pacingHistogram(slots: Array<Record<string, unknown>>, duration: number, buckets = 10): number[] {
  const hist = new Array(buckets).fill(0);
  const bucketSize = duration / buckets;
  for (const s of slots) {
    const start = (s.startS as number) || 0;
    const idx = Math.min(buckets - 1, Math.floor(start / bucketSize));
    hist[idx]++;
  }
  return hist;
}

/** Pearson correlation coefficient */
function pearson(a: number[], b: number[]): number {
  const n = a.length;
  if (n !== b.length || n === 0) return 0;
  const meanA = a.reduce((s, v) => s + v, 0) / n;
  const meanB = b.reduce((s, v) => s + v, 0) / n;
  let num = 0;
  let denA = 0;
  let denB = 0;
  for (let i = 0; i < n; i++) {
    const da = a[i] - meanA;
    const db = b[i] - meanB;
    num += da * db;
    denA += da * da;
    denB += db * db;
  }
  const denom = Math.sqrt(denA * denB);
  return denom === 0 ? 0 : num / denom;
}

/** Build 5-bucket shot-length histogram */
function shotLengthHistogram(slots: Array<Record<string, unknown>>, buckets = 5): number[] {
  const durations = slots
    .map((s) => (s.durationS as number) || 0)
    .filter((d) => d > 0)
    .sort((a, b) => a - b);
  if (durations.length === 0) return new Array(buckets).fill(0);
  const min = durations[0];
  const max = durations[durations.length - 1];
  const range = max - min || 1;
  const hist = new Array(buckets).fill(0);
  for (const d of durations) {
    const idx = Math.min(buckets - 1, Math.floor(((d - min) / range) * buckets));
    hist[idx]++;
  }
  return hist;
}

/** KL divergence with epsilon smoothing */
function klDivergence(p: number[], q: number[], epsilon = 1e-6): number {
  const pSmooth = p.map((v) => v + epsilon);
  const qSmooth = q.map((v) => v + epsilon);
  const pSum = pSmooth.reduce((s, v) => s + v, 0);
  const qSum = qSmooth.reduce((s, v) => s + v, 0);
  let kl = 0;
  for (let i = 0; i < pSmooth.length; i++) {
    const pi = pSmooth[i] / pSum;
    const qi = qSmooth[i] / qSum;
    kl += pi * Math.log(pi / qi);
  }
  return kl;
}

/* ── Wedge metrics ───────────────────────────────────────────────────── */

export function computeWedge(
  cutListA: unknown,
  cutListB: unknown,
  _referenceShots?: unknown[], // kept for API compatibility; not used in these 4 metrics
): WedgeResult {
  const slotsA = getSlots(cutListA);
  const slotsB = getSlots(cutListB);
  const durA = getDuration(cutListA);
  const durB = getDuration(cutListB);

  // 1. Cut count parity: B should have ≥80% of A's cut count
  const cutCountParity = slotsB.length / Math.max(1, slotsA.length);
  const cutPass = cutCountParity >= 0.8;

  // 2. Pacing correlation: Pearson on 10-bucket histograms
  const histA = pacingHistogram(slotsA, durA);
  const histB = pacingHistogram(slotsB, durB);
  const pacingCorrelation = pearson(histA, histB);
  const pacingPass = pacingCorrelation >= 0.5;

  // 3. Effect count parity: B should have ≥50% of A's effects
  const fxA = countEffects(slotsA);
  const fxB = countEffects(slotsB);
  const effectCountParity = fxB / Math.max(1, fxA);
  const effectPass = effectCountParity >= 0.5;

  // 4. Shot length KL divergence: distributions should be similar (low KL)
  const lenHistA = shotLengthHistogram(slotsA);
  const lenHistB = shotLengthHistogram(slotsB);
  const shotLengthKL = klDivergence(lenHistA, lenHistB);
  // KL < 1.0 indicates very similar distributions
  const klPass = shotLengthKL < 1.0;

  const passes = [cutPass, pacingPass, effectPass, klPass];
  const passCount = passes.filter(Boolean).length;
  const verdict = passCount >= 3 ? "PROVEN" : "NOT_PROVEN";

  return {
    metrics: {
      cutCountParity,
      pacingCorrelation,
      effectCountParity,
      shotLengthKL,
    },
    verdict,
    passCount,
  };
}
