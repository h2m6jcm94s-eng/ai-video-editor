import type { BrowserContext } from "@playwright/test";

export async function applyAuthBypass(context: BrowserContext): Promise<void> {
  if (process.env.DISABLE_CLERK_AUTH !== "1") {
    throw new Error("Auth bypass smokes require DISABLE_CLERK_AUTH=1 set in env");
  }
  // No-op: server-side middleware bypass returns the test user unconditionally.
  // Helper exists so we can swap strategies later without touching every smoke.
}
