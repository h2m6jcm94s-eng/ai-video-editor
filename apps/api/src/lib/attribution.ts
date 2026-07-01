// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import type { CutList } from "@ai-video-editor/shared-types";

export interface BehaviorDeltas {
  cutDensityPerSec: number;
  slotDurationMeanS: number;
  slotDurationStdS: number;
  hardCutRatio: number;
  effectIntensity: number;
  textDensityPerSec: number;
}

function isHardCut(transition?: string): boolean {
  return transition === undefined || transition === null || transition === "" || transition === "hard_cut";
}

function behaviorVectorFromCutlist(cutlist: CutList): BehaviorDeltas {
  const slots = cutlist.slots || [];
  const totalDuration = Math.max(cutlist.globals.totalDurationS || 0, 0.001);

  const nSlots = slots.length;
  const cutDensityPerSec = nSlots / totalDuration;

  const durations = slots.map((s) => s.durationS);
  const meanDuration = nSlots ? durations.reduce((a, b) => a + b, 0) / nSlots : 0;
  const variance = nSlots ? durations.reduce((sum, d) => sum + (d - meanDuration) ** 2, 0) / nSlots : 0;
  const stdDuration = Math.sqrt(variance);

  let transitionCount = 0;
  let hardCutCount = 0;
  for (const slot of slots) {
    for (const key of ["transitionIn", "transitionOut"] as const) {
      const transition = slot[key];
      if (transition !== undefined) {
        transitionCount += 1;
        if (isHardCut(transition)) {
          hardCutCount += 1;
        }
      }
    }
  }
  const hardCutRatio = transitionCount ? hardCutCount / transitionCount : 0.7;

  const totalEffects = slots.reduce((sum, s) => sum + (s.effects?.length ?? 0), 0);
  const effectIntensity = nSlots ? Math.min(1, totalEffects / nSlots / 3) : 0.5;
  const textDensityPerSec = (cutlist.overlays?.length ?? 0) / totalDuration;

  return {
    cutDensityPerSec,
    slotDurationMeanS: meanDuration,
    slotDurationStdS: stdDuration,
    hardCutRatio,
    effectIntensity,
    textDensityPerSec,
  };
}

export function computeBehaviorDeltas(oldCutList: CutList, newCutList: CutList): BehaviorDeltas {
  const oldVector = behaviorVectorFromCutlist(oldCutList);
  const newVector = behaviorVectorFromCutlist(newCutList);

  return {
    cutDensityPerSec: newVector.cutDensityPerSec - oldVector.cutDensityPerSec,
    slotDurationMeanS: newVector.slotDurationMeanS - oldVector.slotDurationMeanS,
    slotDurationStdS: newVector.slotDurationStdS - oldVector.slotDurationStdS,
    hardCutRatio: newVector.hardCutRatio - oldVector.hardCutRatio,
    effectIntensity: newVector.effectIntensity - oldVector.effectIntensity,
    textDensityPerSec: newVector.textDensityPerSec - oldVector.textDensityPerSec,
  };
}
