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
