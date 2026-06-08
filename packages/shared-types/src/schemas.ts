import { z } from "zod";
import { STYLE_TIER, EDIT_MODE, ASSET_TYPE } from "./enums";

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

export const createProjectSchema = z.object({
  name: projectNameSchema,
  styleTier: z.enum(STYLE_TIER).default("with_effects"),
  mode: z.enum(EDIT_MODE).default("auto"),
});

export const patchProjectSchema = createProjectSchema.partial();

export const presignedUploadSchema = z.object({
  projectId: z.string().uuid("Invalid project ID"),
  filename: z.string().min(1).max(255),
  mimeType: z.string().refine((v) => ALLOWED_MIMES.includes(v), {
    message: "Invalid MIME type",
  }),
  type: z.enum(ASSET_TYPE),
});

export const updateCutlistSchema = z.object({
  cutList: z.record(z.unknown()),
});

export const promptEditSchema = z.object({
  prompt: z.string().min(1, "Prompt is required").max(2000, "Prompt too long"),
  attachedAssetId: z.string().uuid().optional(),
  contextSlotIndex: z.number().int().nonnegative().optional(),
});

export const createTemplateSchema = z.object({
  name: projectNameSchema,
  description: z.string().max(2000).optional(),
  cutList: z.record(z.unknown()),
  tags: z.array(z.string()).default([]),
  isPublic: z.boolean().default(false),
});

export const createRenderSchema = z.object({
  projectId: z.string().uuid(),
  options: z.record(z.unknown()).optional(),
});

export const providerKeySchema = z.object({
  provider: z.string().min(1),
  key: z.string().min(1),
});

export const testProviderKeySchema = z.object({
  provider: z.string().min(1),
});
