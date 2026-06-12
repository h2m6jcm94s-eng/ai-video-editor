import { expect, test } from "@playwright/test";
import { applyAuthBypass } from "../../helpers/authBypass";

test.describe("Smoke — New Project", () => {
  test.beforeEach(async ({ context }) => {
    await applyAuthBypass(context);
  });

  test("Creating a project navigates to editor", async ({ page }) => {
    await page.goto("/dashboard");
    await page.getByRole("button", { name: "New Project" }).first().click();
    await page.locator("input#project-name").fill("Smoke Test Project");
    await page.locator('[data-testid="create-project-submit"]').click();
    await page.waitForURL(/\/editor\/[a-f0-9-]{36}/, { timeout: 10000 });
    expect(page.url()).toMatch(/\/editor\/[a-f0-9-]{36}/);
  });
});
