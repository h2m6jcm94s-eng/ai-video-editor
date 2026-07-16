import { z } from "zod";

export { EDIT_VERB } from "./verbs.generated";

import { EDIT_VERB } from "./verbs.generated";

export type EditVerb = (typeof EDIT_VERB)[number];

export const trimSlotParamsSchema = z
  .object({
    slotIndex: z.number().int().min(0),
    startS: z.number().min(0).optional(),
    durationS: z.number().min(0.5).optional(),
  })
  .strict();

export const addEffectParamsSchema = z
  .object({
    slotIndex: z.number().int().min(0),
    effectType: z.enum([
      "zoom_punch_in",
      "shake",
      "glitch",
      "vignette",
      "film_grain",
      "color_pop",
      "chromatic_aberration",
      "text_kinetic",
      "lower_third",
      "camera_motion",
    ]),
    startS: z.number().min(0).optional(),
    durationS: z.number().min(0).optional(),
  })
  .strict();

export const addTextOverlayParamsSchema = z
  .object({
    text: z.string().min(1).max(200),
    startS: z.number().min(0),
    durationS: z.number().min(0.5),
    position: z.enum(["center", "top", "bottom"]).default("center"),
  })
  .strict();

export const setTransitionParamsSchema = z
  .object({
    slotIndex: z.number().int().min(0).optional(),
    transition: z.enum(["hard_cut", "fade", "dissolve", "slide", "zoom"]),
  })
  .strict();

export const parsedCommandSchema = z.object({
  verb: z.enum(EDIT_VERB),
  params: z.record(z.unknown()),
  confidence: z.number().min(0).max(1),
  matchedPhrase: z.string(),
});

export type ParsedCommand = z.infer<typeof parsedCommandSchema>;
