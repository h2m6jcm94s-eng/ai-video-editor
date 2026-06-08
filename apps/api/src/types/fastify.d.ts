// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import "fastify";
import type { SignedInAuthObject } from "@clerk/backend";
import type { Project } from "../db/schema";

declare module "fastify" {
  interface FastifyRequest {
    userId: string;
    auth: SignedInAuthObject;
    validatedBody?: unknown;
    project?: Project;
  }
}
