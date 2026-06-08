// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
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

export interface SectionMarker {
  name: string;
  start_s: number;
  end_s: number;
}

export interface PreviewEffects {
  brightness: number; // 0-2, default 1
  contrast: number; // 0-2, default 1
  saturation: number; // 0-2, default 1
  blur: number; // 0-10px, default 0
  sepia: number; // 0-1, default 0
  hueRotate: number; // 0-360, default 0
}

export interface CutListGlobals {
  total_duration_s: number;
  tempo_bpm: number;
  time_signature: string;
  energy_curve: number[];
  section_markers: SectionMarker[];
  aspect_ratio: string;
  effects?: PreviewEffects;
}

export interface Slot {
  index: number;
  start_s: number;
  duration_s: number;
  beat_index: number;
  section: string;
  transition_in: string;
  transition_out: string;
  target_shot_type: string;
  subject_hint: string;
  motion_hint: string;
  energy_level: number;
  required_tags: string[];
  avoid_tags: string[];
  selected_clip_id: string | null;
  ranked_clip_ids: string[] | null;
  confidence: number | null;
}

export interface Overlay {
  id: string;
  type: "text" | "shape" | "effect";
  text?: string;
  start_time: number;
  end_time: number;
  x: number;
  y: number;
  width: number;
  height: number;
  style?: Record<string, unknown>;
}

export interface Subtitle {
  id: string;
  text: string;
  start_s: number;
  end_s: number;
  speaker?: string;
  confidence?: number;
}

export interface CutList {
  globals: CutListGlobals;
  slots: Slot[];
  overlays: Overlay[];
  subtitles?: Subtitle[];
}

export interface BeatGrid {
  bpm: number;
  time_signature: string;
  beats: number[];
  beat_positions: number[];
  segments: { start: number; end: number; label: string }[];
  downbeats: number[];
}

