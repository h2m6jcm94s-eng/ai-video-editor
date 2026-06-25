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
    await page.waitForLoadState("networkidle");

    const nameInput = page.getByRole("textbox", { name: "Project Name" }).first();
    await nameInput.fill("Chaos Test");

    const submit = page.getByRole("button", { name: /create project/i }).first();
    await expect(submit).toBeEnabled({ timeout: 5000 });
    await Promise.all([page.waitForURL(/\/editor\/[a-f0-9-]+/, { timeout: 15_000 }), submit.click()]);

    // Simulate a confused user clicking every visible panel/button.
    await randomEditorClicks(page, 10);
    await closeAnyOpenDialog(page);

    // The app should still be alive.
    await expect(page.locator("body")).toBeVisible();
    await expect(page.locator("body")).not.toHaveText(/application error|something went wrong/i);
  });

  test("Double-clicking submit buttons does not crash", async ({ page }) => {
    await page.goto("/editor/new");
    await page.waitForLoadState("networkidle");

    const nameInput = page.getByRole("textbox", { name: "Project Name" }).first();
    await nameInput.fill("Double Click Test");

    const submit = page.getByRole("button", { name: /create project/i }).first();
    await expect(submit).toBeEnabled({ timeout: 5000 });

    // Simulate a user double-clicking the submit button. Using clickCount keeps
    // both clicks on the same element before navigation, avoiding Playwright
    // re-querying the locator on the post-navigation page.
    await submit.click({ clickCount: 2, timeout: 5000 });

    await expect(page.locator("body")).toBeVisible();
  });
});
