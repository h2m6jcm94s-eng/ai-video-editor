// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.

// ── Re-exports from shared-types (single source of truth) ──
import type {
  SectionMarker,
  AudioTrack,
  Effect,
  Slot,
} from "@ai-video-editor/shared-types";

export type { SectionMarker, AudioTrack, Effect, Slot } from "@ai-video-editor/shared-types";

import type { EffectType, Easing } from "@ai-video-editor/shared-types";

// ── Web-only types (UI state, local shapes, API response wrappers) ──

export interface Project {
  id: string;
  name: string;
  status: "uploading" | "processing" | "complete" | "failed";
  styleTier: string;
  mode: string;
  referenceAssetId: string | null;
  songAssetId: string | null;
  clipAssetIds: string[];
  cutList: CutList | null;
  renderAssetId: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface Asset {
  id: string;
  projectId: string;
  type: "reference" | "song" | "clip";
  filename: string;
  mimeType: string;
  sizeBytes: number;
  durationSec: number | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  storageKey: string;
  storageUrl: string | null;
  metadata: unknown;
  createdAt: string;
}

export interface RenderJob {
  id: string;
  projectId: string;
  status: "queued" | "running" | "complete" | "failed";
  stage: string;
  progress: number;
  workflowId: string | null;
  outputAssetId: string | null;
  previewAssetId: string | null;
  errorMessage: string | null;
  startedAt: string | null;
  completedAt: string | null;
  createdAt: string;
}

export interface PreviewEffects {
  brightness: number; // 0-2, default 1
  contrast: number; // 0-2, default 1
  saturation: number; // 0-2, default 1
  blur: number; // 0-10px, default 0
  sepia: number; // 0-1, default 0
  hueRotate: number; // 0-360, default 0
}

// NOTE: Web Overlay is a canvas UI element (id, geometry, style).
// The API contract overlay (text burn-in spec) lives in shared-types.
// TODO: reconcile these two overlay concepts post-Phase-1.
export interface Overlay {
  id: string;
  type: "text" | "shape" | "effect";
  text?: string;
  startS: number;
  endS: number;
  x: number;
  y: number;
  width: number;
  height: number;
  style?: Record<string, unknown>;
}

export interface Subtitle {
  id: string;
  text: string;
  startS: number;
  endS: number;
  speaker?: string;
  confidence?: number;
}

export interface CutListGlobals {
  totalDurationS: number;
  tempoBpm: number;
  timeSignature: string;
  energyCurve: number[];
  sectionMarkers: SectionMarker[];
  aspectRatio: string;
  effects?: PreviewEffects;
}

export interface CutList {
  globals: CutListGlobals;
  slots: Slot[];
  overlays: Overlay[];
  subtitles?: Subtitle[];
  audioTracks?: AudioTrack[];
}

export interface BeatGrid {
  bpm: number;
  timeSignature: string;
  beats: number[];
  beatPositions: number[];
  segments: { start: number; end: number; label: string }[];
  downbeats: number[];
}

// Kept for backward compat with components that reference effect param shapes
// directly. Prefer importing Effect from shared-types.
export type EffectParams = {
  zoom_punch_in: { targetScale: number; durationMs: number; easing: Easing };
  focus_pull: { targetBlur: number; durationMs: number; easing: Easing };
  freeze_frame: { holdMs: number };
  speed_ramp: { startSpeed: number; endSpeed: number; curve: "linear" | "ramp_up" | "ramp_down" | "s_curve" };
  shake: { intensity: number; durationMs: number };
  glitch: { intensity: number; durationMs: number };
  vignette: { intensity: number; color: string };
  film_grain: { intensity: number };
  color_pop: { hueShift: number; saturation: number };
  text_kinetic: { text: string; animation: "fade_up" | "typewriter" | "pop" | "slide_left"; fontSize: number };
  lower_third: { text: string; subtext?: string; style: "minimal" | "bold" | "news" };
  callout_arrow: { direction: "up" | "down" | "left" | "right"; color: string };
  whoosh_sfx: { variant: "short" | "long" | "dramatic"; gainDb: number };
  ding_sfx: { variant: "bell" | "chime" | "coin"; gainDb: number };
  record_scratch_sfx: { gainDb: number };
};
