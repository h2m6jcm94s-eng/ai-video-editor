import { expect, test } from "@playwright/test";
import { applyAuthBypass } from "../../helpers/authBypass";
import { clickAnywhereWithText, navigateBackAndForward } from "../../helpers/chaos";

test.describe("Chaos — Navigation", () => {
  test.beforeEach(async ({ context }) => {
    await applyAuthBypass(context);
  });

  test("User can click around dashboard and editor without crashing", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page.locator("body")).toBeVisible();

    // Click random navigation-like elements.
    await clickAnywhereWithText(page, "New Project");
    await expect(page.locator("body")).toBeVisible();

    // Navigate back and forward.
    await navigateBackAndForward(page);
    await expect(page.locator("body")).toBeVisible();

    // Try to go to settings and back.
    await page.goto("/settings");
    await expect(page.locator("body")).toBeVisible();
    await navigateBackAndForward(page);
    await expect(page.locator("body")).toBeVisible();
  });

  test("Refresh mid-flow does not crash the editor", async ({ page }) => {
    await page.goto("/editor/new");
    await expect(page.locator("body")).toBeVisible();

    // User starts typing then refreshes.
    const nameInput = page.locator('input[id="name"]').or(page.locator("input#project-name")).first();
    if (await nameInput.isVisible().catch(() => false)) {
      await nameInput.fill("Refresh Test");
    }

    await page.reload();
    await expect(page.locator("body")).toBeVisible();
  });
});
