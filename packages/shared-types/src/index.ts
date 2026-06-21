export * from "./cutlist";
export * from "./effects";
export * from "./enums";
export * from "./errors";
export * from "./schemas";

// ── Inferred contract types (single source of truth) ──
import type { z } from "zod";
import type { effectSchema } from "./effects";
import type {
  audioTrackSchema,
  createProjectSchema,
  createRenderSchema,
  createTemplateSchema,
  cutListGlobalsSchema,
  cutListSchema,
  overlaySchema,
  presignedUploadSchema,
  promptEditSchema,
  providerEncryptedKeySchema,
  providerKeySchema,
  sectionMarkerSchema,
  slotSchema,
  testProviderKeySchema,
} from "./schemas";

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
export type ProviderEncryptedKeyInput = z.infer<typeof providerEncryptedKeySchema>;
export type TestProviderKeyInput = z.infer<typeof testProviderKeySchema>;
