import { z } from "zod";

const schema = z.object({
  DATABASE_URL: z.string().url("DATABASE_URL must be a valid postgres:// URL"),
  CLERK_SECRET_KEY: z.string().min(10, "CLERK_SECRET_KEY is missing or too short"),
  WEB_URL: z.string().url("WEB_URL must be a valid URL (e.g. http://localhost:3000)"),
  R2_ENDPOINT: z.string().url("R2_ENDPOINT must be a valid URL"),
  R2_ACCESS_KEY_ID: z.string().min(1, "R2_ACCESS_KEY_ID is missing"),
  R2_SECRET_ACCESS_KEY: z.string().min(1, "R2_SECRET_ACCESS_KEY is missing"),
  R2_BUCKET_NAME: z.string().min(1, "R2_BUCKET_NAME is missing"),
  REDIS_URL: z.string().url("REDIS_URL must be a valid redis:// URL"),
  TEMPORAL_HOST: z.string().min(1, "TEMPORAL_HOST is missing (e.g. localhost:7233)"),
  API_PORT: z.coerce.number().int().min(1).max(65535).default(4000),
});

const result = schema.safeParse(process.env);
if (!result.success) {
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

export const env = result.data;
