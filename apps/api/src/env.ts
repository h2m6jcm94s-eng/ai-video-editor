// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { config } from "dotenv";
import { z } from "zod";

config({ path: ".env.local" });

const isTest = process.env.NODE_ENV === "test";

// Set test-mode defaults on process.env so all modules see them
if (isTest) {
  process.env.GUARDRAILS_ENABLED = "false";
  // Force test KEK so mock encrypted keys in tests can be decrypted.
  // .env.local may contain a real KEK, but tests use data encrypted with the test KEK.
  process.env.PROVIDER_KEK = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f";
  // Prevent .env.local's AI_PROVIDER_TOOLCALL from hijacking applyPromptEdit in tests.
  // Tests that need it can vi.stubEnv() after this point.
  delete process.env.AI_PROVIDER_TOOLCALL;
  // Force test internal worker token so webhook auth tests pass regardless of .env.local
  process.env.INTERNAL_WORKER_TOKEN = "test-internal-token-1234567890abcdef";
  // Prevent Clerk-free E2E flags from leaking into unit tests.
  delete process.env.DISABLE_CLERK_AUTH;
  delete process.env.E2E;
}

const schema = z.object({
  DATABASE_URL: z
    .string()
    .url("DATABASE_URL must be a valid postgres:// URL")
    .default("postgresql://localhost:5432/test"),
  CLERK_SECRET_KEY: z.string().min(1, "CLERK_SECRET_KEY is missing").default("sk_test_dummy"),
  WEB_URL: z
    .string()
    .url("WEB_URL must be a valid URL (e.g. http://localhost:3000)")
    .default("http://localhost:3000"),
  R2_ENDPOINT: z.string().url("R2_ENDPOINT must be a valid URL").default("http://localhost:9000"),
  R2_ACCESS_KEY_ID: z.string().min(1, "R2_ACCESS_KEY_ID is missing").default("minioadmin"),
  R2_SECRET_ACCESS_KEY: z.string().min(1, "R2_SECRET_ACCESS_KEY is missing").default("minioadmin"),
  R2_BUCKET_NAME: z.string().min(1, "R2_BUCKET_NAME is missing").default("test"),
  REDIS_URL: z.string().url("REDIS_URL must be a valid redis:// URL").default("redis://localhost:6379"),
  TEMPORAL_HOST: z
    .string()
    .min(1, "TEMPORAL_HOST is missing (e.g. localhost:7233)")
    .default("localhost:7233"),
  API_PORT: z.coerce.number().int().min(1).max(65535).default(4000),
  GUARDRAILS_URL: z.string().url().optional(),
  GUARDRAILS_TIMEOUT_MS: z.coerce.number().int().min(100).max(30000).default(3000),
  GUARDRAILS_ENABLED: z.enum(["true", "false"]).default("true"),
  DEFAULT_DAILY_TOKEN_LIMIT: z.coerce.number().int().min(1000).default(100000),
  INTERNAL_WORKER_TOKEN: z.string().min(32, "INTERNAL_WORKER_TOKEN must be at least 32 characters"),
  PROVIDER_KEK: z
    .string()
    .length(64, "PROVIDER_KEK must be exactly 64 hex characters (32 bytes)")
    .regex(/^[0-9a-fA-F]+$/, "PROVIDER_KEK must be a hex string")
    .optional(),
});

const result = schema.safeParse(process.env);

if (!result.success && !isTest) {
  console.error("\n╔══════════════════════════════════════════════════╗");
  console.error("║  STARTUP FAILED — Missing or invalid env vars    ║");
  console.error("╠══════════════════════════════════════════════════╣");
  for (const issue of result.error.issues) {
    console.error(`║  ✗  ${issue.path[0]}: ${issue.message}`);
  }
  console.error("╠══════════════════════════════════════════════════╣");
  console.error("║  Copy infra/.env.example → .env and fill values  ║");
  console.error("╚══════════════════════════════════════════════════╝\n");
  process.exit(1);
}

// In test mode, schema defaults fill in any missing vars so Vitest can run without real services.
export const env = result.success ? result.data : schema.parse({});
