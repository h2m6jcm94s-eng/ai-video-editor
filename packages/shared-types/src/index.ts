export interface User {
  id: string;
  email: string;
  name?: string;
  createdAt: Date;
}

export interface Project {
  id: string;
  userId: string;
  name: string;
  status: ProjectStatus;
  referenceAssetId?: string;
  songAssetId?: string;
  clipAssetIds: string[];
  cutList?: CutList;
  renderAssetId?: string;
  styleTier: StyleTier;
  mode: EditMode;
  createdAt: Date;
  updatedAt: Date;
}

export type ProjectStatus =
  | "uploading"
  | "analyzing"
  | "generating_cutlist"
  | "review_pending"
  | "rendering"
  | "preview_ready"
  | "completed"
  | "failed";

export type StyleTier = "cuts_only" | "with_color" | "with_text" | "full_style";
export type EditMode = "auto" | "assisted";

export interface Asset {
  id: string;
  projectId: string;
  type: AssetType;
  filename: string;
  mimeType: string;
  sizeBytes: number;
  durationSec?: number;
  width?: number;
  height?: number;
  fps?: number;
  storageKey: string;
  storageUrl: string;
  metadata?: Record<string, unknown>;
  createdAt: Date;
}

export type AssetType = "reference_video" | "user_clip" | "song" | "render" | "preview" | "lut";

export interface CutList {
  globals: CutListGlobals;
  slots: Slot[];
  overlays: Overlay[];
}

export interface CutListGlobals {
  totalDurationS: number;
  tempoBpm: number;
  timeSignature: string;
  key?: string;
  energyCurve: number[];
  sectionMarkers: SectionMarker[];
  colorGradeRef?: string;
  aspectRatio: string;
}

export interface SectionMarker {
  name: string;
  startS: number;
  endS: number;
}

export interface Slot {
  index: number;
  startS: number;
  durationS: number;
  beatIndex: number;
  section: string;
  transitionIn: TransitionType;
  transitionOut: TransitionType;
  targetShotType: ShotType;
  subjectHint: string;
  motionHint: MotionHint;
  energyLevel: number;
  requiredTags: string[];
  avoidTags: string[];
  selectedClipId?: string;
  rankedClipIds?: string[];
  confidence?: number;
}

export type TransitionType =
  | "hard_cut"
  | "fade"
  | "dissolve"
  | "wipe_left"
  | "wipe_right"
  | "wipe_up"
  | "wipe_down"
  | "circle_open"
  | "slide_up"
  | "slide_down"
  | "slide_left"
  | "slide_right"
  | "pixelize"
  | "hlslice"
  | "flash"
  | "whip";

export type ShotType =
  | "extreme_wide"
  | "wide"
  | "medium_wide"
  | "medium"
  | "medium_close_up"
  | "close_up"
  | "extreme_close_up"
  | "insert"
  | "establishing";

export type MotionHint =
  | "static"
  | "slow_push"
  | "fast_push"
  | "pull"
  | "pan_left"
  | "pan_right"
  | "tilt_up"
  | "tilt_down"
  | "whip"
  | "zoom_in"
  | "zoom_out"
  | "dolly_in"
  | "dolly_out"
  | "tracking"
  | "handheld"
  | "gimbal"
  | "drone"
  | "crane"
  | "speed_ramp"
  | "freeze";

export interface Overlay {
  text: string;
  startS: number;
  endS: number;
  position: OverlayPosition;
  font: string;
  fontSizePx: number;
  color: string;
  stroke?: string;
  animation: OverlayAnimation;
}

export type OverlayPosition =
  | "center"
  | "top"
  | "bottom"
  | "left"
  | "right"
  | "top_left"
  | "top_right"
  | "bottom_left"
  | "bottom_right";

export type OverlayAnimation =
  | "none"
  | "fade"
  | "slide"
  | "typewriter"
  | "scale"
  | "pop"
  | "word_by_word";

export interface ShotBoundary {
  startFrame: number;
  endFrame: number;
  startS: number;
  endS: number;
  isGradual: boolean;
  confidence: number;
}

export interface BeatGrid {
  bpm: number;
  beats: number[];
  downbeats: number[];
  beatPositions: number[];
  segments: BeatSegment[];
}

export interface BeatSegment {
  start: number;
  end: number;
  label: string;
}

export interface ShotAnalysis {
  shotSize: ShotType;
  motion: MotionHint;
  subjectType: string;
  lighting: string;
  dominantColor: string;
  cameraMove: string;
}

export interface StyleAnalysis {
  colorPalette: string[];
  contrastLevel: number;
  saturationLevel: number;
  brightnessLevel: number;
  lutExtracted: boolean;
  lutStorageKey?: string;
  detectedTransitions: TransitionType[];
  detectedOverlays: Overlay[];
  cameraMotions: MotionHint[];
  pacing: string;
  mood: string;
}

export interface ClipScore {
  clipId: string;
  semanticScore: number;
  shotTypeScore: number;
  aestheticScore: number;
  motionScore: number;
  durationScore: number;
  diversityPenalty: number;
  totalScore: number;
}

export interface RenderJob {
  id: string;
  projectId: string;
  status: RenderStatus;
  stage: string;
  progress: number;
  outputAssetId?: string;
  previewAssetId?: string;
  errorMessage?: string;
  startedAt?: Date;
  completedAt?: Date;
}

export type RenderStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export interface ProgressEvent {
  jobId: string;
  stage: string;
  progress: number;
  message: string;
  timestamp: Date;
}
