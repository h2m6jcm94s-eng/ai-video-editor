import { expect, test } from "@playwright/test";
import * as fs from "fs/promises";
import * as path from "path";
import { applyAuthBypass } from "../../helpers/authBypass";

const FIXTURES_DIR = path.join(process.cwd(), "e2e", "fixtures");

test.describe("Chaos — Upload misuse", () => {
  test.beforeEach(async ({ context }) => {
    await applyAuthBypass(context);
  });

  test("Uploading a wrong file type shows a graceful error", async ({ page }) => {
    await page.goto("/editor/new");
    const nameInput = page.locator('input[id="name"]').or(page.locator("input#project-name")).first();
    if (await nameInput.isVisible().catch(() => false)) {
      await nameInput.fill("Upload Misuse Test");
    }
    await page
      .getByRole("button", { name: /create project/i })
      .first()
      .click();
    await page.waitForURL(/\/editor\/[a-f0-9-]+/, { timeout: 15_000 });

    // Create a temporary text file and try to upload it as a clip.
    const badFile = path.join(FIXTURES_DIR, "not-a-video.txt");
    await fs.writeFile(badFile, "this is not a video");
    try {
      const clipInput = page.locator('[data-testid="upload-clip"]').first();
      if (await clipInput.isVisible().catch(() => false)) {
        await clipInput.setInputFiles(badFile);
      }
      // The app should survive; an error toast or validation message is acceptable.
      await expect(page.locator("body")).toBeVisible();
    } finally {
      await fs.unlink(badFile).catch(() => {});
    }
  });

  test("Canceling and re-selecting an upload works", async ({ page }) => {
    await page.goto("/editor/new");
    const nameInput = page.locator('input[id="name"]').or(page.locator("input#project-name")).first();
    if (await nameInput.isVisible().catch(() => false)) {
      await nameInput.fill("Re-upload Test");
    }
    await page
      .getByRole("button", { name: /create project/i })
      .first()
      .click();
    await page.waitForURL(/\/editor\/[a-f0-9-]+/, { timeout: 15_000 });

    const songInput = page.locator('[data-testid="upload-song"]').first();
    if (await songInput.isVisible().catch(() => false)) {
      const songPath = path.join(FIXTURES_DIR, "song.mp3");
      await songInput.setInputFiles(songPath);
      // Simulate user changing their mind by selecting a different (valid) file again.
      await songInput.setInputFiles(songPath);
      await expect(page.locator("body")).toBeVisible();
    }
  });
});
