import { expect, test } from "@playwright/test";
import { applyAuthBypass } from "../../helpers/authBypass";
import { closeAnyOpenDialog, randomEditorClicks } from "../../helpers/chaos";

test.describe("Chaos — Editor actions", () => {
  test.beforeEach(async ({ context }) => {
    await applyAuthBypass(context);
  });

  test("Random clicks in the editor do not crash the app", async ({ page }) => {
    // Create a project first so the editor is fully loaded.
    await page.goto("/editor/new");
    const nameInput = page.locator('input[id="name"]').or(page.locator("input#project-name")).first();
    if (await nameInput.isVisible().catch(() => false)) {
      await nameInput.fill("Chaos Test");
    }
    await page
      .getByRole("button", { name: /create project/i })
      .first()
      .click();
    await page.waitForURL(/\/editor\/[a-f0-9-]+/, { timeout: 15_000 });

    // Simulate a confused user clicking every visible panel/button.
    await randomEditorClicks(page, 10);
    await closeAnyOpenDialog(page);

    // The app should still be alive.
    await expect(page.locator("body")).toBeVisible();
    await expect(page.locator("body")).not.toHaveText(/application error|something went wrong/i);
  });

  test("Double-clicking submit buttons does not crash", async ({ page }) => {
    await page.goto("/editor/new");
    const nameInput = page.locator('input[id="name"]').or(page.locator("input#project-name")).first();
    if (await nameInput.isVisible().catch(() => false)) {
      await nameInput.fill("Double Click Test");
    }
    const submit = page.getByRole("button", { name: /create project/i }).first();
    await submit.click();
    await submit.click().catch(() => {});
    await expect(page.locator("body")).toBeVisible();
  });
});
