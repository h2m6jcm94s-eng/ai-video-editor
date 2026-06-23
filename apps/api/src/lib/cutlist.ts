// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
import type { CutList, Effect, Slot } from "@ai-video-editor/shared-types";
import {
  audioTrackSchema,
  buildInitialCutList,
  effectSchema,
  overlaySchema,
} from "@ai-video-editor/shared-types";

interface AssetLike {
  id: string;
  type: string;
  filename?: string | null;
  durationSec?: number | null;
}

function normalizeEffect(effect: Record<string, unknown>, slotDurationS: number) {
  const draft = {
    ...effect,
    startS: typeof effect.startS === "number" ? effect.startS : 0,
    durationS: typeof effect.durationS === "number" ? effect.durationS : slotDurationS,
    params: effect.params && typeof effect.params === "object" ? effect.params : {},
  };
  const parsed = effectSchema.safeParse(draft);
  return parsed.success ? parsed.data : null;
}

function normalizeSlot(slot: Record<string, unknown>, index: number, clipIds: string[]): Slot {
  const startS = typeof slot.startS === "number" ? slot.startS : index * 5;
  const durationS = typeof slot.durationS === "number" ? slot.durationS : 5;
  let selectedClipId = typeof slot.selectedClipId === "string" ? slot.selectedClipId : undefined;
  if (!selectedClipId && clipIds.length > 0) {
    selectedClipId = clipIds[index % clipIds.length];
  }
  const rawEffects = Array.isArray(slot.effects) ? slot.effects : [];
  const effects = rawEffects
    .map((e) => normalizeEffect((e as Record<string, unknown>) || {}, durationS))
    .filter((e): e is Effect => e !== null);

  const normalized: Slot = {
    index: typeof slot.index === "number" ? slot.index : index,
    startS,
    durationS,
    beatIndex: typeof slot.beatIndex === "number" ? slot.beatIndex : index,
    section: typeof slot.section === "string" && slot.section ? slot.section : "verse",
    transitionIn: typeof slot.transitionIn === "string" ? slot.transitionIn : "hard_cut",
    transitionOut: typeof slot.transitionOut === "string" ? slot.transitionOut : "hard_cut",
    targetShotType:
      typeof slot.targetShotType === "string" && slot.targetShotType ? slot.targetShotType : "medium",
    subjectHint: typeof slot.subjectHint === "string" && slot.subjectHint ? slot.subjectHint : "person",
    motionHint: typeof slot.motionHint === "string" && slot.motionHint ? slot.motionHint : "static",
    energyLevel: typeof slot.energyLevel === "number" ? slot.energyLevel : 0.5,
    requiredTags: Array.isArray(slot.requiredTags) ? slot.requiredTags : [],
    avoidTags: Array.isArray(slot.avoidTags) ? slot.avoidTags : [],
    effects,
    maskEnabled: typeof slot.maskEnabled === "boolean" ? slot.maskEnabled : true,
  };

  if (selectedClipId) {
    normalized.selectedClipId = selectedClipId;
    normalized.rankedClipIds = Array.isArray(slot.rankedClipIds)
      ? (slot.rankedClipIds as string[])
      : [selectedClipId];
  } else if (Array.isArray(slot.rankedClipIds)) {
    normalized.rankedClipIds = slot.rankedClipIds as string[];
  }

  if (typeof slot.maskAssetId === "string") {
    normalized.maskAssetId = slot.maskAssetId;
  }

  return normalized;
}

function normalizeOverlay(overlay: Record<string, unknown>) {
  const parsed = overlaySchema.safeParse(overlay);
  return parsed.success ? parsed.data : null;
}

function normalizeAudioTrack(track: Record<string, unknown>) {
  const parsed = audioTrackSchema.safeParse(track);
  return parsed.success ? parsed.data : null;
}

export function normalizeCutList(cutList: Record<string, unknown>, assets?: AssetLike[]): CutList {
  const globals = (cutList.globals as Record<string, unknown>) || {};
  const rawSlots = Array.isArray(cutList.slots) ? cutList.slots : [];
  const clipIds = (assets || []).filter((a) => a.type === "clip").map((a) => a.id);

  const slots = rawSlots.map((s, i) => normalizeSlot((s as Record<string, unknown>) || {}, i, clipIds));
  const totalDurationS =
    typeof globals.totalDurationS === "number"
      ? globals.totalDurationS
      : slots.reduce((sum, s) => sum + (s.durationS || 0), 0) || 30;

  const rawOverlays = Array.isArray(cutList.overlays) ? cutList.overlays : [];
  const overlays = rawOverlays
    .map((o) => normalizeOverlay((o as Record<string, unknown>) || {}))
    .filter(Boolean);

  const rawAudioTracks = Array.isArray(cutList.audioTracks) ? cutList.audioTracks : [];
  const audioTracks = rawAudioTracks
    .map((t) => normalizeAudioTrack((t as Record<string, unknown>) || {}))
    .filter(Boolean);

  return {
    globals: {
      totalDurationS,
      tempoBpm: typeof globals.tempoBpm === "number" ? globals.tempoBpm : 120,
      timeSignature: typeof globals.timeSignature === "string" ? globals.timeSignature : "4/4",
      energyCurve: Array.isArray(globals.energyCurve) ? globals.energyCurve : [0.5],
      sectionMarkers: Array.isArray(globals.sectionMarkers)
        ? globals.sectionMarkers
        : [{ name: "full", startS: 0, endS: totalDurationS }],
      aspectRatio: typeof globals.aspectRatio === "string" ? globals.aspectRatio : "9:16",
      key: typeof globals.key === "string" ? globals.key : undefined,
      colorGradeRef: typeof globals.colorGradeRef === "string" ? globals.colorGradeRef : undefined,
    },
    slots,
    overlays,
    audioTracks,
  } as CutList;
}

export { buildInitialCutList };
