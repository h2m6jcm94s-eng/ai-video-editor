// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { z } from "zod";
import type { FastifyRequest, FastifyReply } from "fastify";

export const ALLOWED_MIMES = [
  "video/mp4",
  "video/quicktime",
  "video/webm",
  "audio/mpeg",
  "audio/wav",
  "audio/aac",
  "audio/ogg",
];

export const createProjectSchema = z.object({
  name: z.string().min(1).max(255),
  styleTier: z.enum(["cuts_only", "with_color", "with_text", "full_style"]).optional(),
  mode: z.enum(["auto", "assisted"]).optional(),
});

export const patchProjectSchema = z.object({
  name: z.string().min(1).max(255).optional(),
  styleTier: z.enum(["cuts_only", "with_color", "with_text", "full_style"]).optional(),
  mode: z.enum(["auto", "assisted"]).optional(),
});

export const presignedUploadSchema = z.object({
  projectId: z.string().uuid(),
  filename: z.string().min(1).max(255),
  mimeType: z.string().refine((v) => ALLOWED_MIMES.includes(v), {
    message: "Invalid MIME type",
  }),
  type: z.enum(["reference_video", "song", "clip", "render"]),
  partNumber: z.number().optional(),
  uploadId: z.string().optional(),
});

export const createRenderSchema = z.object({
  projectId: z.string().uuid(),
  options: z.record(z.unknown()).optional(),
});

export const updateCutlistSchema = z.object({
  cutList: z.object({
    globals: z.object({
      total_duration_s: z.number().optional(),
      tempo_bpm: z.number().optional(),
      time_signature: z.string().optional(),
    }).passthrough(),
    slots: z.array(z.object({
      index: z.number().int(),
      start_s: z.number(),
      duration_s: z.number(),
      beat_index: z.number().int().optional(),
      section: z.string().optional(),
      transition_in: z.string().optional(),
      transition_out: z.string().optional(),
      target_shot_type: z.string().optional(),
      subject_hint: z.string().optional(),
      motion_hint: z.string().optional(),
      energy_level: z.number().min(0).max(1).optional(),
      required_tags: z.array(z.string()).optional(),
      avoid_tags: z.array(z.string()).optional(),
      selected_clip_id: z.string().nullable().optional(),
      ranked_clip_ids: z.array(z.string()).optional(),
      confidence: z.number().optional(),
    }).passthrough()),
    overlays: z.array(z.record(z.unknown())).optional(),
  }),
});

export function validateBody<T>(schema: z.ZodSchema<T>) {
  return async (request: FastifyRequest, reply: FastifyReply) => {
    const result = schema.safeParse(request.body);
    if (!result.success) {
      return reply.status(422).send({
        error: "Validation failed",
        code: "VALIDATION_ERROR",
        details: result.error.issues,
      });
    }
    request.validatedBody = result.data;
  };
}
