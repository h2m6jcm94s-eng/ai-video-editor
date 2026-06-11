import type { Page } from "@playwright/test";

const EMAIL = process.env.E2E_TEST_USER_EMAIL;
const PASSWORD = process.env.E2E_TEST_USER_PASSWORD;

export async function signIn(page: Page): Promise<void> {
  if (!EMAIL || !PASSWORD) {
    throw new Error("E2E_TEST_USER_EMAIL and E2E_TEST_USER_PASSWORD must be set in env");
  }

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

  // Wait for navigation to dashboard
  await page.waitForURL("/dashboard", { timeout: 15_000 });
}
