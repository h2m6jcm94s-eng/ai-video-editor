import { z } from "zod";
import { effectSchema } from "./effects";
import { ASSET_TYPE, EDIT_MODE, STYLE_TIER } from "./enums";

export const ALLOWED_MIMES = [
  "video/mp4",
  "video/quicktime",
  "video/webm",
  "audio/mpeg",
  "audio/wav",
  "audio/aac",
  "audio/ogg",
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
    key: z.string().optional(),
    energyCurve: z.array(z.number()).default([]),
    sectionMarkers: z.array(sectionMarkerSchema).default([]),
    colorGradeRef: z.string().optional(),
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
    effects: z.array(effectSchema).default([]),
  })
  .strict();

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
  })
  .strict();

export const audioTrackSchema = z
  .object({
    assetId: z.string().min(1),
    gainDb: z.number().min(-60).max(12).default(0),
    startS: z.number().min(0),
    endS: z.number().min(0),
    fadeInS: z.number().min(0).default(0),
    fadeOutS: z.number().min(0).default(0),
  })
  .strict();

export const cutListSchema = z
  .object({
    globals: cutListGlobalsSchema,
    slots: z.array(slotSchema).min(1, "Cut list must have at least one slot"),
    overlays: z.array(overlaySchema).default([]),
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

export const renderOptionsSchema = z
  .object({
    exportPreset: z.enum(["youtube_16_9", "reels_9_16", "tiktok_9_16", "square_1_1"]).optional(),
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
  .regex(/^[A-Za-z0-9+/=]+$/, "Encrypted key must be base64");

export const testProviderKeySchema = z
  .object({
    provider: z.string().min(1),
  })
  .strict();
