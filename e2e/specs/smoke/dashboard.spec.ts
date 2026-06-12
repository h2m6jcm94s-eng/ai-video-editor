import { expect, test } from "@playwright/test";
import { applyAuthBypass } from "../../helpers/authBypass";

test.describe("Smoke — Dashboard", () => {
  test.beforeEach(async ({ context }) => {
    await applyAuthBypass(context);
  });

  test("New Project button is visible on /dashboard", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page.getByRole("button", { name: "New Project" }).first()).toBeVisible({ timeout: 5000 });
  });
});
