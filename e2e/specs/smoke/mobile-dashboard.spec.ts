import { expect, test } from "@playwright/test";

test.describe("Mobile smoke", () => {
  test("dashboard and pricing render without horizontal overflow", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page.getByText("Your Projects")).toBeVisible();
    const dashboardWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const viewportWidth = await page.evaluate(() => window.innerWidth);
    expect(dashboardWidth).toBeLessThanOrEqual(viewportWidth);

    await page.goto("/pricing");
    await expect(page.getByText("Simple pricing")).toBeVisible();
    const pricingWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(pricingWidth).toBeLessThanOrEqual(viewportWidth);
  });
});
