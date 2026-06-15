import path from "node:path";
import { expect, test } from "@playwright/test";
import { applyAuthBypass } from "../../helpers/authBypass";

test.describe("Smoke — Upload Reference + Song", () => {
  test.beforeEach(async ({ context }) => {
    await applyAuthBypass(context);
  });

  test("Uploading reference and song sets clean UUID columns", async ({ page, request }) => {
    const res = await request.post("http://localhost:4000/api/projects", {
      data: { name: "Upload Reference Song Test", styleTier: "with_effects", mode: "auto" },
    });
    const payload = await res.json();
    const projectId = payload.project?.id ?? payload.id;

    await page.goto(`/editor/${projectId}`);
    await page.waitForLoadState("networkidle");

    await page.locator("input#upload-reference").setInputFiles(path.resolve("e2e/fixtures/reference.mp4"));
    await expect(page.locator('[data-testid^="asset-"]')).toHaveCount(1, { timeout: 30000 });
    await expect(page.locator('[data-testid^="asset-"]').first()).toHaveAttribute("data-state", "ingested", {
      timeout: 60000,
    });

    await page.locator("input#upload-song").setInputFiles(path.resolve("e2e/fixtures/song.mp3"));
    await expect(page.locator('[data-testid^="asset-"]')).toHaveCount(2, { timeout: 30000 });
    await expect(page.locator('[data-testid^="asset-"]').last()).toHaveAttribute("data-state", "ingested", {
      timeout: 60000,
    });

    const projectRes = await request.get(`http://localhost:4000/api/projects/${projectId}`);
    const projectData = await projectRes.json();
    expect(projectData.project?.referenceAssetId).toMatch(/^[a-f0-9-]{36}$/);
    expect(projectData.project?.songAssetId).toMatch(/^[a-f0-9-]{36}$/);
  });
});
