export interface WedgeMetrics {
  slotDensityA: number;
  slotDensityB: number;
  shotTypeDiversityA: number;
  shotTypeDiversityB: number;
  transitionVarietyA: number;
  transitionVarietyB: number;
  referenceSimilarityB: number;
}

export interface WedgeResult {
  metrics: WedgeMetrics;
  verdict: "PROVEN" | "FAIL";
  passCount: number;
}

export function computeWedge(cutListA: unknown, cutListB: unknown, referenceShots?: unknown[]): WedgeResult {
  const a = cutListA as Record<string, unknown> | null;
  const b = cutListB as Record<string, unknown> | null;

  const aSlots = (a?.slots as unknown[]) || [];
  const bSlots = (b?.slots as unknown[]) || [];
  const aGlobals = (a?.globals as Record<string, unknown>) || {};
  const bGlobals = (b?.globals as Record<string, unknown>) || {};

  const aDur = (aGlobals.totalDurationS as number) || 60;
  const bDur = (bGlobals.totalDurationS as number) || 60;

  // 1. Slot density (slots per minute)
  const slotDensityA = aSlots.length / (aDur / 60);
  const slotDensityB = bSlots.length / (bDur / 60);
  const densityPass = slotDensityB >= slotDensityA * 0.8;

  // 2. Shot type diversity
  const aShotTypes = new Set(
    aSlots.map((s) => (s as Record<string, unknown>).targetShotType as string).filter(Boolean),
  );
  const bShotTypes = new Set(
    bSlots.map((s) => (s as Record<string, unknown>).targetShotType as string).filter(Boolean),
  );
  const shotTypeDiversityA = aShotTypes.size;
  const shotTypeDiversityB = bShotTypes.size;
  const diversityPass = bShotTypes.size >= aShotTypes.size;

  // 3. Transition variety
  const aTransitions = new Set(
    aSlots.map((s) => (s as Record<string, unknown>).transitionIn as string).filter(Boolean),
  );
  const bTransitions = new Set(
    bSlots.map((s) => (s as Record<string, unknown>).transitionIn as string).filter(Boolean),
  );
  const transitionVarietyA = aTransitions.size;
  const transitionVarietyB = bTransitions.size;
  const transitionPass = bTransitions.size >= aTransitions.size;

  // 4. Reference similarity (B should use shot types that appear in reference)
  let referenceSimilarityB = 0;
  let similarityPass = true;
  if (referenceShots && referenceShots.length > 0) {
    const refShotTypes = new Set(
      referenceShots.map((s) => (s as Record<string, unknown>).type as string).filter(Boolean),
    );
    const matching = Array.from(bShotTypes).filter((t) => refShotTypes.has(t)).length;
    referenceSimilarityB = refShotTypes.size > 0 ? matching / refShotTypes.size : 1;
    similarityPass = referenceSimilarityB >= 0.5;
  }

  const passes = [densityPass, diversityPass, transitionPass, similarityPass];
  const passCount = passes.filter(Boolean).length;
  const verdict = passCount >= 3 ? "PROVEN" : "FAIL";

  return {
    metrics: {
      slotDensityA,
      slotDensityB,
      shotTypeDiversityA,
      shotTypeDiversityB,
      transitionVarietyA,
      transitionVarietyB,
      referenceSimilarityB,
    },
    verdict,
    passCount,
  };
}
