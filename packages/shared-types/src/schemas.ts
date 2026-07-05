import { z } from "zod";
import { effectSchema } from "./effects";
import { ASSET_TYPE, EDIT_MODE, EXPORT_PRESETS, STYLE_TIER } from "./enums";

export const ALLOWED_MIMES = [
  "video/mp4",
  "video/quicktime",
  "video/webm",
  "audio/mpeg",
  "audio/wav",
  "audio/aac",
  "audio/ogg",
  "audio/flac",
  "application/vnd.adobe.cube",
  "application/octet-stream",
];

export const projectNameSchema = z
  .string()
  .trim()
  .min(1, "Name is required")
  .max(255, "Name must be 255 characters or less");

export const createProjectSchema = z
  .object({
    name: projectNameSchema,
    styleTier: z.enum(STYLE_TIER).default("with_effects"),
    mode: z.enum(EDIT_MODE).default("auto"),
  })
  .strict();

export const patchProjectSchema = z
  .object({
    name: projectNameSchema.optional(),
    styleTier: z.enum(STYLE_TIER).optional(),
    mode: z.enum(EDIT_MODE).optional(),
    excludeFromLearning: z.boolean().optional(),
  })
  .strict();

export const presignedUploadSchema = z
  .object({
    projectId: z.string().uuid("Invalid project ID"),
    filename: z.string().min(1).max(255),
    mimeType: z.string().refine((v) => ALLOWED_MIMES.includes(v), {
      message: "Invalid MIME type",
    }),
    type: z.enum(ASSET_TYPE),
  })
  .strict();

export const sectionMarkerSchema = z
  .object({
    name: z.string().min(1),
    startS: z.number().min(0),
    endS: z.number().min(0),
  })
  .strict();

export const cutListGlobalsSchema = z
  .object({
    totalDurationS: z.number().min(0),
    tempoBpm: z.number().min(0),
    timeSignature: z.string().default("4/4"),
    key: z.string().nullish(),
    energyCurve: z.array(z.number()).default([]),
    sectionMarkers: z.array(sectionMarkerSchema).default([]),
    colorGradeRef: z.string().nullish(),
    aspectRatio: z.string().default("9:16"),
  })
  .strict();

export const slotSchema = z
  .object({
    index: z.number().int().min(0),
    startS: z.number().min(0),
    durationS: z.number().min(0),
    beatIndex: z.number().int().min(0),
    section: z.string().min(1),
    transitionIn: z.string().default("hard_cut"),
    transitionOut: z.string().default("hard_cut"),
    targetShotType: z.string().min(1),
    subjectHint: z.string().min(1),
    motionHint: z.string().min(1),
    energyLevel: z.number().min(0).max(1).default(0.5),
    requiredTags: z.array(z.string()).default([]),
    avoidTags: z.array(z.string()).default([]),
    selectedClipId: z.string().optional(),
    rankedClipIds: z.array(z.string()).optional(),
    confidence: z.number().min(0).max(1).optional(),
    maskAssetId: z.string().nullish(),
    maskEnabled: z.boolean().default(true),
    identityIdsPresent: z.array(z.number().int()).default([]),
    protagonistMatteEnabled: z.boolean().default(true),
    enableKineticText: z.boolean().default(false),
    textZLayer: z.enum(["on_top", "behind_subject"]).default("on_top"),
    textDensity: z.enum(["low", "medium", "high"]).default("medium"),
    kineticText: z.string().optional(),
    kineticTextStyle: z.string().optional(),
    kineticTextColor: z.string().optional(),
    kineticTextAnimation: z.string().optional(),
    effects: z.array(effectSchema).default([]),
    sourceWindowStartS: z.number().min(0).optional(),
    anticipationOffsetS: z.number().default(0),
  })
  .strict();

export const wordTimingSchema = z.object({
  text: z.string().min(1),
  startS: z.number().min(0),
  endS: z.number().min(0),
  isEmphasis: z.boolean().default(false),
});

export const overlaySchema = z
  .object({
    text: z.string().min(1),
    startS: z.number().min(0),
    endS: z.number().min(0),
    position: z.string().default("center"),
    font: z.string().default("Inter"),
    fontSizePx: z.number().int().min(1).default(48),
    color: z.string().default("#FFFFFF"),
    stroke: z.string().optional(),
    animation: z.string().default("none"),
    highlightColor: z.string().optional(),
    words: z.array(wordTimingSchema).optional(),
    emphasisWords: z.array(z.string()).default([]),
  })
  .strict();

export const subtitleSchema = z
  .object({
    id: z.string().min(1),
    text: z.string().min(1),
    startS: z.number().min(0),
    endS: z.number().min(0),
    speaker: z.string().optional(),
    confidence: z.number().min(0).max(1).optional(),
  })
  .strict();

export const audioTrackSchema = z
  .object({
    assetId: z.string().min(1),
    role: z.enum(["music", "dialogue", "voiceover", "sfx", "ambience"]).default("music"),
    gainDb: z.number().min(-60).max(12).default(0),
    startS: z.number().min(0),
    endS: z.number().min(0),
    fadeInS: z.number().min(0).default(0),
    fadeOutS: z.number().min(0).default(0),
    duckGainDb: z.number().min(-60).max(0).default(-12),
    duckAttackMs: z.number().min(1).max(1000).default(20),
    duckReleaseMs: z.number().min(10).max(2000).default(250),
    duckThreshold: z.number().min(0).max(1).default(0.05),
  })
  .strict();

export const cutListSchema = z
  .object({
    globals: cutListGlobalsSchema,
    slots: z.array(slotSchema).min(1, "Cut list must have at least one slot"),
    overlays: z.array(overlaySchema).default([]),
    subtitles: z.array(subtitleSchema).default([]),
    audioTracks: z.array(audioTrackSchema).default([]),
  })
  .strict();

export const updateCutlistSchema = z
  .object({
    cutList: cutListSchema,
  })
  .strict();

export const promptEditSchema = z
  .object({
    prompt: z.string().min(1, "Prompt is required").max(2000, "Prompt too long"),
    attachedAssetId: z.string().uuid().optional(),
    contextSlotIndex: z.number().int().nonnegative().optional(),
  })
  .strict();

export const createTemplateSchema = z
  .object({
    name: projectNameSchema,
    description: z.string().max(2000).optional(),
    cutList: cutListSchema,
    tags: z.array(z.string()).default([]),
    isPublic: z.boolean().default(false),
  })
  .strict();

export const createRenderSchema = z
  .object({
    projectId: z.string().uuid(),
    options: z.record(z.unknown()).optional(),
  })
  .strict();

export const adaptiveFeaturesSchema = z
  .object({
    useAdaptiveSlotDensity: z.boolean().optional(),
    useAdaptiveAudioPolicy: z.boolean().optional(),
    useIconicQuoteDetection: z.boolean().optional(),
    useEmotionLedCuts: z.boolean().optional(),
    useCorpusKnn: z.boolean().optional(),
    usePerUserBias: z.boolean().optional(),
  })
  .strict()
  .optional();

export const renderOptionsSchema = z
  .object({
    exportPreset: z.enum(["auto", "youtube_16_9", "reels_9_16", "tiktok_9_16", "square_1_1"]).optional(),
    durationSec: z.number().min(5).max(600).optional(),
    adaptiveFeatures: adaptiveFeaturesSchema,
  })
  .strict();

export const patchRenderOutcomeSchema = z
  .object({
    thumbsUp: z.boolean().optional(),
    explicitRating: z.number().int().min(1).max(5).optional(),
    thumbComment: z.string().max(2000).optional(),
    abandoned: z.boolean().optional(),
  })
  .strict();

export const saveRenderOutcomeSchema = z
  .object({
    exported: z.boolean().optional(),
    downloaded: z.boolean().optional(),
    regenerated: z.boolean().optional(),
    abandoned: z.boolean().optional(),
    editCount: z.number().int().min(0).optional(),
    inferredQualityScore: z.number().min(0).max(1).optional(),
    retention30sPercent: z.number().min(0).max(100).optional(),
    totalViews: z.number().int().min(0).optional(),
    isFinalized: z.boolean().optional(),
  })
  .strict();

export const generationOptionsSchema = z
  .object({
    durationSec: z.number().min(1).max(300).optional(),
    adaptiveFeatures: adaptiveFeaturesSchema,
  })
  .strict()
  .optional();

export const generateFromReferenceSchema = z
  .object({
    prompt: z.string().min(1).max(2000).optional(),
    options: generationOptionsSchema,
  })
  .strict();

export const templateMetaSchema = createTemplateSchema.omit({ cutList: true });

export const PROVIDER_KEY_OPTIONS = [
  "anthropic",
  "openai",
  "kimi",
  "openrouter",
  "groq",
  "gemini",
  "qwen",
] as const;

export const providerKeySchema = z
  .object({
    provider: z.enum(PROVIDER_KEY_OPTIONS, { message: "Select a supported provider" }),
    key: z
      .string()
      .min(8, "API key is too short")
      .max(2048, "Key too long")
      .regex(/^[^\s]+$/, "Key cannot contain whitespace"),
  })
  .strict();

export const providerEncryptedKeySchema = z
  .string()
  .min(16, "Encrypted key is too short")
  .max(4096, "Encrypted key is too long")
  .regex(/^(v\d+:)?[A-Za-z0-9+/=]+$/, "Encrypted key must be base64 with an optional vN: prefix");

export const patchTemplateSchema = z
  .object({
    name: z.string().min(1).max(255).optional(),
    description: z.string().max(2000).optional(),
    cutList: z.unknown().optional(),
    tags: z.array(z.string().max(50)).max(20).optional(),
    isPublic: z.boolean().optional(),
  })
  .strict();

export const testProviderKeySchema = z
  .object({
    provider: z.string().min(1),
  })
  .strict();

export const styleGenomeFamilySchema = z.object({
  totalCuts: z.number().optional(),
  avgCutDurationS: z.number().optional(),
  stdCutDurationS: z.number().optional(),
  minCutDurationS: z.number().optional(),
  maxCutDurationS: z.number().optional(),
  cutDensityPerMin: z.number().optional(),
  verseCutDensity: z.number().optional(),
  chorusCutDensity: z.number().optional(),
  dropCutDensity: z.number().optional(),
  introCutDensity: z.number().optional(),
  outroCutDensity: z.number().optional(),
  buildUpCutDensity: z.number().optional(),
  hardCutRatio: z.number().optional(),
  gradualTransitionRatio: z.number().optional(),
  cutsOnDownbeatRatio: z.number().optional(),
  cutsOffBeatRatio: z.number().optional(),
  avgMotionEnergy: z.number().optional(),
  maxMotionEnergy: z.number().optional(),
  motionEnergyStd: z.number().optional(),
  pctStillShots: z.number().optional(),
  pctPanLeft: z.number().optional(),
  pctPanRight: z.number().optional(),
  pctTiltUp: z.number().optional(),
  pctTiltDown: z.number().optional(),
  pctZoomIn: z.number().optional(),
  pctZoomOut: z.number().optional(),
  pctHandheld: z.number().optional(),
  pctGimbal: z.number().optional(),
  avgFaceSizeRatio: z.number().optional(),
  maxFaceSizeRatio: z.number().optional(),
  avgSubjectsPerShot: z.number().optional(),
  pctShotsWithFace: z.number().optional(),
  avgFaceScreenTimeS: z.number().optional(),
  protagonistPresentRatio: z.number().optional(),
  avgShotSubjectCount: z.number().optional(),
  faceSizeVariance: z.number().optional(),
  cutToBeatAlignment: z.number().optional(),
  cutToDownbeatAlignment: z.number().optional(),
  verseCutToBeatRatio: z.number().optional(),
  chorusCutToBeatRatio: z.number().optional(),
  dropCutToBeatRatio: z.number().optional(),
  avgCutToNearestBeatS: z.number().optional(),
  musicDuckFrequency: z.number().optional(),
  dialogueClipRatio: z.number().optional(),
  iconicLineCount: z.number().optional(),
  avgDialogueDurationS: z.number().optional(),
  dominantShotSize: z.enum(["close_up", "medium", "wide"]).optional(),
  pctCloseUp: z.number().optional(),
  pctMediumShot: z.number().optional(),
  pctWideShot: z.number().optional(),
  ruleOfThirdsRatio: z.number().optional(),
});

export const styleGenomeSchema = z
  .object({
    version: z.string(),
    featureCount: z.number().int().nonnegative(),
    families: z.record(styleGenomeFamilySchema),
    extractedAt: z.string().datetime().or(z.string()),
  })
  .strict();
