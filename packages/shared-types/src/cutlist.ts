// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.

import { z } from "zod";
import { cutListSchema, slotSchema } from "./schemas";

type CutList = z.infer<typeof cutListSchema>;
type Slot = z.infer<typeof slotSchema>;

interface AssetLike {
  id: string;
  type: string;
  filename?: string | null;
  durationSec?: number | null;
}

/**
 * Build a canonical initial cut list from a project's assets.
 * Clips become slots; a song (if present) sets the duration and audio track.
 */
export function buildInitialCutList(assets: AssetLike[]): CutList {
  const clips = assets.filter((a) => a.type === "clip");
  const song = assets.find((a) => a.type === "song");
  const totalDuration = Math.min(
    song?.durationSec || clips.reduce((s, c) => s + (c.durationSec || 5), 0) || 30,
    30,
  );
  const slotCount = Math.max(1, clips.length || 1);
  const slotDuration = totalDuration / slotCount;

  const slots: Slot[] = Array.from({ length: slotCount }).map((_, i) => {
    const clip = clips[i % clips.length];
    return {
      index: i,
      startS: i * slotDuration,
      durationS: slotDuration,
      beatIndex: i,
      section: i === 0 ? "intro" : i === slotCount - 1 ? "outro" : "verse",
      transitionIn: i === 0 ? "hard_cut" : "dissolve",
      transitionOut: i === slotCount - 1 ? "hard_cut" : "dissolve",
      targetShotType: ["wide", "medium", "close_up"][i % 3],
      subjectHint: "person",
      motionHint: "static",
      energyLevel: 0.5,
      requiredTags: [],
      avoidTags: [],
      selectedClipId: clip?.id,
      rankedClipIds: clip ? [clip.id] : undefined,
      maskAssetId: undefined,
      maskEnabled: true,
      identityIdsPresent: [],
      protagonistMatteEnabled: true,
      enableKineticText: false,
      textZLayer: "on_top",
      textDensity: "medium",
      kineticText: undefined,
      effects: [],
      sourceWindowStartS: undefined,
      anticipationOffsetS: 0,
    };
  });

  return {
    globals: {
      totalDurationS: totalDuration,
      tempoBpm: 120,
      timeSignature: "4/4",
      energyCurve: [0.5],
      sectionMarkers: [{ name: "full", startS: 0, endS: totalDuration }],
      aspectRatio: "9:16",
    },
    slots,
    overlays: [],
    subtitles: [],
    audioTracks: song
      ? [
          {
            assetId: song.id,
            role: "music",
            startS: 0,
            endS: totalDuration,
            gainDb: 0,
            fadeInS: 0,
            fadeOutS: 0,
            duckGainDb: -12,
            duckAttackMs: 20,
            duckReleaseMs: 250,
            duckThreshold: 0.05,
          },
        ]
      : [],
  };
}
