export const STYLE_TIER = [
  "cuts_only",
  "color_grade",
  "with_text",
  "with_effects",
  "full_remix",
] as const;

export const EDIT_MODE = ["auto", "assisted"] as const;

export const ASSET_TYPE = [
  "reference_video",
  "song",
  "clip",
  "render",
  "preview",
  "subtitle",
  "lut",
  "sfx",
] as const;

export const PROJECT_STATUS = [
  "uploading",
  "processing",
  "complete",
  "failed",
] as const;

export const RENDER_STATUS = [
  "queued",
  "running",
  "complete",
  "failed",
] as const;

export const ERROR_CODE = [
  "VALIDATION_ERROR",
  "UNAUTHORIZED",
  "FORBIDDEN",
  "NOT_FOUND",
  "CONFLICT",
  "RATE_LIMITED",
  "INTERNAL_ERROR",
  "PROVIDER_KEY_MISSING",
] as const;

export type StyleTier = (typeof STYLE_TIER)[number];
export type EditMode = (typeof EDIT_MODE)[number];
export type AssetType = (typeof ASSET_TYPE)[number];
export type ProjectStatus = (typeof PROJECT_STATUS)[number];
export type RenderStatus = (typeof RENDER_STATUS)[number];
export type ErrorCode = (typeof ERROR_CODE)[number];
