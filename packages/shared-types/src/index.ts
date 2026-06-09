export * from "./enums";
export * from "./schemas";
export * from "./errors";
export * from "./effects";

// ── Inferred contract types (single source of truth) ──
import type { z } from "zod";
import type {
  cutListSchema,
  slotSchema,
  overlaySchema,
  audioTrackSchema,
  cutListGlobalsSchema,
  sectionMarkerSchema,
  createProjectSchema,
  presignedUploadSchema,
  promptEditSchema,
  createRenderSchema,
  createTemplateSchema,
  providerKeySchema,
  testProviderKeySchema,
} from "./schemas";
import type { effectSchema } from "./effects";

export type CutList = z.infer<typeof cutListSchema>;
export type Slot = z.infer<typeof slotSchema>;
export type Overlay = z.infer<typeof overlaySchema>;
export type AudioTrack = z.infer<typeof audioTrackSchema>;
export type CutListGlobals = z.infer<typeof cutListGlobalsSchema>;
export type SectionMarker = z.infer<typeof sectionMarkerSchema>;
export type Effect = z.infer<typeof effectSchema>;
export type CreateProjectInput = z.infer<typeof createProjectSchema>;
export type PresignedUploadInput = z.infer<typeof presignedUploadSchema>;
export type PromptEditInput = z.infer<typeof promptEditSchema>;
export type RenderInput = z.infer<typeof createRenderSchema>;
export type CreateTemplateInput = z.infer<typeof createTemplateSchema>;
export type ProviderKeyInput = z.infer<typeof providerKeySchema>;
export type TestProviderKeyInput = z.infer<typeof testProviderKeySchema>;
