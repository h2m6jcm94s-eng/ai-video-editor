export const STYLE_TIER = ["cuts_only", "color_grade", "with_text", "with_effects", "full_remix"] as const;

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
  "mask",
] as const;

export const PROJECT_STATUS = ["uploading", "processing", "complete", "failed"] as const;

export const RENDER_STATUS = ["queued", "running", "complete", "failed"] as const;

export const EXPORT_PRESETS = [
  { value: "youtube_16_9", label: "YouTube 16:9", width: 1280, height: 720 },
  { value: "reels_9_16", label: "Instagram Reels 9:16", width: 720, height: 1280 },
  { value: "tiktok_9_16", label: "TikTok 9:16", width: 720, height: 1280 },
  { value: "square_1_1", label: "Square 1:1", width: 720, height: 720 },
] as const;

export type StyleTier = (typeof STYLE_TIER)[number];
export type EditMode = (typeof EDIT_MODE)[number];
export type AssetType = (typeof ASSET_TYPE)[number];
export type ProjectStatus = (typeof PROJECT_STATUS)[number];
export type RenderStatus = (typeof RENDER_STATUS)[number];
