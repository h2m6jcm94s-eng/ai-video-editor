import { createClerkClient } from "@clerk/backend";

const secretKey = process.env.CLERK_SECRET_KEY;
if (!secretKey) {
  throw new Error("CLERK_SECRET_KEY must be set in env for E2E testing tokens");
}

const clerkClient = createClerkClient({ secretKey });

let cached: { token: string; expiresAt: number } | null = null;

export async function getTestingToken(): Promise<string> {
  const now = Date.now();
  if (cached && cached.expiresAt > now + 30_000) {
    return cached.token;
  }

  const result = await clerkClient.testingTokens.createTestingToken();
  cached = {
    token: result.token,
    expiresAt: new Date(result.expiresAt).getTime(),
  };
  return cached.token;
}
