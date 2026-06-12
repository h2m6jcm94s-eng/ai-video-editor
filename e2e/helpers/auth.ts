import type { Page } from "@playwright/test";
import { getTestingToken } from "./clerkTestingToken";

const EMAIL = process.env.E2E_TEST_USER_EMAIL;
const PASSWORD = process.env.E2E_TEST_USER_PASSWORD;

export async function signIn(page: Page): Promise<void> {
  if (!EMAIL || !PASSWORD) {
    throw new Error("E2E_TEST_USER_EMAIL and E2E_TEST_USER_PASSWORD must be set in env");
  }

  const token = await getTestingToken();

  // Inject the Clerk testing token as a query param on every Frontend API request.
  // Clerk's JS SDK reads __clerk_testing_token and bypasses bot detection + new-device challenges.
  let interceptCount = 0;
  await page.route(
    (url) => url.hostname.endsWith(".clerk.accounts.dev"),
    (route) => {
      interceptCount += 1;
      const url = new URL(route.request().url());
      if (!url.searchParams.has("__clerk_testing_token")) {
        url.searchParams.set("__clerk_testing_token", token);
      }
      route.continue({ url: url.toString() });
    },
  );
  page.on("close", () => console.log(`[clerk testing token] intercepted ${interceptCount} requests`));

  await page.goto("/sign-in");

  // Clerk SignIn component — Playwright pierces open shadow DOM
  const emailInput = page.locator('input[name="identifier"]').first();
  await emailInput.waitFor({ state: "visible", timeout: 10_000 });
  await emailInput.fill(EMAIL);

  // Click Continue (first step)
  const continueBtn = page.locator('button:has-text("Continue")').first();
  await continueBtn.click();

  // Wait for password field to appear
  const passwordInput = page.locator('input[name="password"]').first();
  await passwordInput.waitFor({ state: "visible", timeout: 10_000 });
  await passwordInput.fill(PASSWORD);

  // Click Continue (second step — sign in)
  await continueBtn.click();

  // Wait for sign-in to complete (URL leaves /sign-in/*)
  await page.waitForURL((url) => !url.pathname.startsWith("/sign-in"), { timeout: 15_000 });

  // Navigate to dashboard explicitly (Clerk may redirect to / by default)
  if (!page.url().includes("/dashboard")) {
    await page.goto("/dashboard");
  }
  await page.waitForURL("**/dashboard", { timeout: 10_000 });
}
