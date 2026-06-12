import { expect, test } from "@playwright/test";
import { applyAuthBypass } from "../../helpers/authBypass";

test.describe("Smoke — Editor Mount", () => {
  test.beforeEach(async ({ context }) => {
    await applyAuthBypass(context);
  });

  test("Editor renders without error boundary fallback", async ({ page, request }) => {
    const res = await request.post("http://localhost:4000/api/projects", {
      data: { name: "Editor Mount Test", styleTier: "with_effects", mode: "auto" },
    });
    expect(res.ok()).toBeTruthy();
    const payload = await res.json();
    const projectId = payload.project?.id ?? payload.id;

    const consoleErrors: string[] = [];
    page.on("pageerror", (err) => consoleErrors.push(err.message));

    await page.goto(`/editor/${projectId}`);
    await page.waitForLoadState("networkidle", { timeout: 10000 });

    await expect(page.locator('[data-testid="editor-topbar"]')).toBeVisible({ timeout: 10000 });

    const hasMaxDepth = consoleErrors.some((e) => e.includes("Maximum update depth"));
    expect(hasMaxDepth).toBeFalsy();
  });
});
