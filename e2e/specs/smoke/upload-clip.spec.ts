import path from "node:path";
import { expect, test } from "@playwright/test";
import { applyAuthBypass } from "../../helpers/authBypass";

test.describe("Smoke — Upload Clip", () => {
  test.beforeEach(async ({ context }) => {
    await applyAuthBypass(context);
  });

  test("Uploading a clip ingests and stores clean UUID array", async ({ page, request }) => {
    const res = await request.post("http://localhost:4000/api/projects", {
      data: { name: "Upload Clip Test", styleTier: "with_effects", mode: "auto" },
    });
    const payload = await res.json();
    const projectId = payload.project?.id ?? payload.id;

    await page.goto(`/editor/${projectId}`);
    await page.waitForLoadState("networkidle");

    const fixturePath = path.resolve("e2e/fixtures/clip-1.mp4");
    await page.locator("input#upload-clip").setInputFiles(fixturePath);

    const assetRow = page.locator('[data-testid^="asset-"]').first();
    // On mobile the media panel can be collapsed, so only require the row to
    // exist in the DOM (not necessarily be visible) before checking its state.
    await assetRow.waitFor({ state: "attached", timeout: 30000 });
    await expect(assetRow).toHaveAttribute("data-state", "ingested", { timeout: 60000 });

    const projectRes = await request.get(`http://localhost:4000/api/projects/${projectId}`);
    const projectData = await projectRes.json();
    expect(Array.isArray(projectData.project?.clipAssetIds)).toBe(true);
    expect(projectData.project.clipAssetIds.length).toBe(1);
    expect(projectData.project.clipAssetIds[0]).toMatch(/^[a-f0-9-]{36}$/);
  });
});
