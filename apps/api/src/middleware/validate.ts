// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.

import {
  ALLOWED_MIMES,
  createProjectSchema,
  createRenderSchema,
  createTemplateSchema,
  patchProjectSchema,
  patchTemplateSchema,
  presignedUploadSchema,
  promptEditSchema,
  renderOptionsSchema,
  updateCutlistSchema,
} from "@ai-video-editor/shared-types";
import type { FastifyReply, FastifyRequest } from "fastify";
import { z } from "zod";
import { sendError } from "../lib/errors";

// Re-export shared schemas so routes can import from one place
export {
  ALLOWED_MIMES,
  createProjectSchema,
  createRenderSchema,
  createTemplateSchema,
  patchProjectSchema,
  patchTemplateSchema,
  presignedUploadSchema,
  promptEditSchema,
  renderOptionsSchema,
  updateCutlistSchema,
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
