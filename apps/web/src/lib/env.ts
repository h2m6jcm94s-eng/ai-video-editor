const REQUIRED_PUBLIC = [
  "NEXT_PUBLIC_API_URL",
  "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY",
] as const;

export function validateClientEnv() {
  const missing = REQUIRED_PUBLIC.filter((k) => !process.env[k]);
  if (missing.length > 0) {
    throw new Error(
      `Missing required env vars:\n${missing.map((k) => `  • ${k}`).join("\n")}\n` +
        "Copy apps/web/.env.example → apps/web/.env.local and fill values."
    );
  }
}
