// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { z } from "zod";
import type { FastifyRequest, FastifyReply } from "fastify";
import {
  ALLOWED_MIMES,
  createProjectSchema,
  patchProjectSchema,
  presignedUploadSchema,
  createRenderSchema,
  updateCutlistSchema,
  promptEditSchema,
  createTemplateSchema,
} from "@ai-video-editor/shared-types";
import { sendError } from "../lib/errors";

export { ALLOWED_MIMES };

// Re-export shared schemas so routes can import from one place
export {
  createProjectSchema,
  patchProjectSchema,
  presignedUploadSchema,
  createRenderSchema,
  updateCutlistSchema,
  promptEditSchema,
  createTemplateSchema,
};

export function validateBody<T>(schema: z.ZodSchema<T>) {
  return async (request: FastifyRequest, reply: FastifyReply) => {
    const result = schema.safeParse(request.body);
    if (!result.success) {
      return sendError(reply, 422, "Validation failed", "VALIDATION_ERROR", result.error.issues);
    }
    request.validatedBody = result.data;
  };
}
