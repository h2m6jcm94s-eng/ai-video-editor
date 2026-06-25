import type { Page } from "@playwright/test";

/**
 * Helpers for "chaotic user" e2e tests — interactions that simulate a real
 * user clicking around without knowing the exact DOM structure.
 *
 * All helpers use short action timeouts and swallow recoverable errors so that
 * a single stuck element cannot hang the whole chaos suite.
 */

const CLICK_TIMEOUT = 3000;

/** Click the first clickable element matching a human-readable label. */
export async function clickByLabel(page: Page, label: string): Promise<void> {
  const locator = page
    .locator("button:not([disabled]), a, [role='button']:not([disabled]), [role='link']")
    .filter({ hasText: new RegExp(label, "i") })
    .first();
  await locator.click({ timeout: CLICK_TIMEOUT }).catch(() => {});
}

/** Click any visible actionable element by partial text (buttons, links, menu items). */
export async function clickAnywhereWithText(page: Page, text: string): Promise<boolean> {
  const locator = page
    .locator("button:not([disabled]), a, [role='button']:not([disabled]), [role='link']")
    .filter({ hasText: new RegExp(text, "i") })
    .first();
  const visible = await locator.isVisible().catch(() => false);
  if (!visible) return false;
  await locator.click({ timeout: CLICK_TIMEOUT }).catch(() => {});
  return true;
}

/** Try to open and close every dialog/popover the user can reach. */
export async function closeAnyOpenDialog(page: Page): Promise<boolean> {
  // Common dismiss patterns: Escape key, clicking a Cancel/Close button, or clicking the overlay.
  await page.keyboard.press("Escape");
  const closed = await page
    .locator("[role='dialog']")
    .count()
    .then((c) => c === 0);
  if (closed) return true;

  const cancel = page
    .locator("[role='dialog']")
    .locator("button:not([disabled])")
    .filter({ hasText: /cancel|close|done|×/i })
    .first();
  const visible = await cancel.isVisible().catch(() => false);
  if (!visible) return false;
  await cancel.click({ timeout: CLICK_TIMEOUT }).catch(() => {});
  return true;
}

/** Perform a small set of random, safe clicks inside the editor. */
export async function randomEditorClicks(page: Page, count = 5): Promise<void> {
  const candidates = [
    "AI Prompt",
    "Render",
    "Media",
    "Timeline",
    "Inspector",
    "Preview",
    "Save",
    "Templates",
    "Settings",
    "New Project",
  ];
  for (let i = 0; i < count; i++) {
    const text = candidates[Math.floor(Math.random() * candidates.length)];
    try {
      await clickAnywhereWithText(page, text);
      // Brief pause so any async UI updates can settle.
      await page.waitForTimeout(200);
      await closeAnyOpenDialog(page);
    } catch {
      // Ignore individual click failures — the goal is to survive the chaos.
    }
  }
}

/** Navigate back and forward like a user exploring the browser history. */
export async function navigateBackAndForward(page: Page): Promise<void> {
  await page.goBack({ timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(300);
  await page.goForward({ timeout: 5000 }).catch(() => {});
}
