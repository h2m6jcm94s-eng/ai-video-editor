import { z } from "zod";

export const EFFECT_TYPE = [
  "zoom_punch_in",
  "focus_pull",
  "freeze_frame",
  "speed_ramp",
  "shake",
  "glitch",
  "vignette",
  "film_grain",
  "color_pop",
  "text_kinetic",
  "lower_third",
  "callout_arrow",
  "whoosh_sfx",
  "ding_sfx",
  "record_scratch_sfx",
] as const;

export type EffectType = (typeof EFFECT_TYPE)[number];

export const EASING = ["linear", "easeIn", "easeOut", "easeInOut"] as const;
export type Easing = (typeof EASING)[number];

const baseEffectSchema = z.object({
  id: z.string().uuid().nullish(),
  startS: z.number().min(0),
  durationS: z.number().min(0),
});

const zoomPunchInSchema = baseEffectSchema.extend({
  type: z.literal("zoom_punch_in"),
  params: z.object({
    targetScale: z.number().min(1).max(3).default(1.3),
    durationMs: z.number().int().min(50).max(2000).default(300),
    easing: z.enum(EASING).default("easeOut"),
  }),
});

const focusPullSchema = baseEffectSchema.extend({
  type: z.literal("focus_pull"),
  params: z.object({
    targetBlur: z.number().min(0).max(20).default(0),
    durationMs: z.number().int().min(50).max(5000).default(800),
    easing: z.enum(EASING).default("easeInOut"),
  }),
});

const freezeFrameSchema = baseEffectSchema.extend({
  type: z.literal("freeze_frame"),
  params: z.object({ holdMs: z.number().int().min(50).max(5000).default(500) }),
});

const speedRampSchema = baseEffectSchema.extend({
  type: z.literal("speed_ramp"),
  params: z.object({
    startSpeed: z.number().min(0.1).max(4).default(1),
    endSpeed: z.number().min(0.1).max(4).default(2),
    curve: z.enum(["linear", "ramp_up", "ramp_down", "s_curve"]).default("s_curve"),
  }),
});

const shakeSchema = baseEffectSchema.extend({
  type: z.literal("shake"),
  params: z.object({
    intensity: z.number().min(0).max(20).default(5),
    durationMs: z.number().int().min(50).max(2000).default(300),
  }),
});

const glitchSchema = baseEffectSchema.extend({
  type: z.literal("glitch"),
  params: z.object({
    intensity: z.number().min(0).max(1).default(0.3),
    durationMs: z.number().int().min(50).max(2000).default(200),
  }),
});

const vignetteSchema = baseEffectSchema.extend({
  type: z.literal("vignette"),
  params: z.object({
    intensity: z.number().min(0).max(1).default(0.4),
    color: z.string().default("#000000"),
  }),
});

const filmGrainSchema = baseEffectSchema.extend({
  type: z.literal("film_grain"),
  params: z.object({ intensity: z.number().min(0).max(1).default(0.2) }),
});

const colorPopSchema = baseEffectSchema.extend({
  type: z.literal("color_pop"),
  params: z.object({
    hueShift: z.number().min(-180).max(180).default(0),
    saturation: z.number().min(0).max(3).default(1.5),
  }),
});

const textKineticSchema = baseEffectSchema.extend({
  type: z.literal("text_kinetic"),
  params: z.object({
    text: z.string().min(1).max(200),
    animation: z.enum(["fade_up", "typewriter", "pop", "slide_left"]).default("fade_up"),
    fontSize: z.number().int().min(8).max(200).default(48),
  }),
});

const lowerThirdSchema = baseEffectSchema.extend({
  type: z.literal("lower_third"),
  params: z.object({
    text: z.string().min(1).max(200),
    subtext: z.string().max(200).optional(),
    style: z.enum(["minimal", "bold", "news"]).default("minimal"),
  }),
});

const calloutArrowSchema = baseEffectSchema.extend({
  type: z.literal("callout_arrow"),
  params: z.object({
    direction: z.enum(["up", "down", "left", "right"]).default("down"),
    color: z.string().default("#f59e0b"),
  }),
});

const whooshSfxSchema = baseEffectSchema.extend({
  type: z.literal("whoosh_sfx"),
  params: z.object({
    variant: z.enum(["short", "long", "dramatic"]).default("short"),
    gainDb: z.number().min(-60).max(12).default(-6),
  }),
});

const dingSfxSchema = baseEffectSchema.extend({
  type: z.literal("ding_sfx"),
  params: z.object({
    variant: z.enum(["bell", "chime", "coin"]).default("bell"),
    gainDb: z.number().min(-60).max(12).default(-6),
  }),
});

const recordScratchSfxSchema = baseEffectSchema.extend({
  type: z.literal("record_scratch_sfx"),
  params: z.object({ gainDb: z.number().min(-60).max(12).default(-3) }),
});

export const effectSchema = z.union([
  zoomPunchInSchema,
  focusPullSchema,
  freezeFrameSchema,
  speedRampSchema,
  shakeSchema,
  glitchSchema,
  vignetteSchema,
  filmGrainSchema,
  colorPopSchema,
  textKineticSchema,
  lowerThirdSchema,
  calloutArrowSchema,
  whooshSfxSchema,
  dingSfxSchema,
  recordScratchSfxSchema,
]);

export type Effect = z.infer<typeof effectSchema>;
