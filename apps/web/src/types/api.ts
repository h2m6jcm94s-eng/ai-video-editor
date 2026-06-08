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

export interface CutListGlobals {
  total_duration_s: number;
  tempo_bpm: number;
  time_signature: string;
  energy_curve: number[];
  section_markers: string[];
  aspect_ratio: string;
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

export interface CutList {
  globals: CutListGlobals;
  slots: Slot[];
  overlays: Overlay[];
}

export interface BeatGrid {
  bpm: number;
  time_signature: string;
  beats: number[];
  beat_positions: number[];
  segments: { start: number; end: number; label: string }[];
  downbeats: number[];
}

export class APIError extends Error {
  status: number;
  code: string;
  details?: unknown;

  constructor(message: string, status: number, code: string, details?: unknown) {
    super(message);
    this.name = "APIError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}
