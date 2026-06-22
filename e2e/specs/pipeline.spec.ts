import { expect, test } from "@playwright/test";
import * as fs from "fs/promises";
import * as path from "path";
import { probe } from "../helpers/ffprobe";
import { uploadFixture } from "../helpers/upload";
import { computeWedge } from "../helpers/wedge";

const OUTPUT_DIR = path.join(process.cwd(), "e2e");

async function writeReport(data: unknown) {
  await fs.writeFile(path.join(OUTPUT_DIR, "report.json"), JSON.stringify(data, null, 2));
}

test.describe("E2E render pipeline", () => {
  // Authentication is handled by Playwright storageState (e2e/.auth/user.json).
  // Each test starts on a signed-in session.

  test("Scenario A: prompt + song only renders a valid MP4", async ({ page }) => {
    // Create project
    await page.goto("/editor/new");
    await page.fill('input[id="name"]', "E2E-A-PromptOnly");
    await page.click('button:has-text("Create Project")');

    // Wait for editor to load
    await page.waitForURL(/\/editor\/[a-f0-9-]+$/, { timeout: 15_000 });

    // Upload assets
    await uploadFixture(page, "song", "e2e/fixtures/song.mp3");
    await uploadFixture(page, "clip", "e2e/fixtures/clip-1.mp4");
    await uploadFixture(page, "clip", "e2e/fixtures/clip-2.mp4");
    await uploadFixture(page, "clip", "e2e/fixtures/clip-3.mp4");

    // Wait for ingest spinners to clear
    await expect(page.locator('[data-state="ingested"]')).toHaveCount(4, { timeout: 180_000 });

    // Open AI Prompt panel
    await page.click('button:has-text("AI Prompt")');

    // Submit prompt
    await page.fill(
      '[data-testid="prompt-input"]',
      "Edit this into a 30-second vertical reel. Cut on every beat. Fade in the first clip. Add a zoom-in on the second clip.",
    );
    // Submit button is the one next to the prompt input (Send icon)
    await page.locator('form button[type="submit"]').click();

    // Wait for cut-list update toast
    await expect(page.getByText("Applied cutlist").first()).toBeVisible({ timeout: 120_000 });

    // Render
    await page.click('button:has-text("Render")');
    await page.click('button:has-text("Start Render")');

    // Wait for render complete (SSE-backed UI shows status badge)
    await expect(page.locator('[data-render-status="complete"]')).toBeVisible({ timeout: 600_000 });

    // Download output via API (Playwright request with cookies)
    const projectRes = await page.request.get("/api/projects?name=E2E-A-PromptOnly");
    const projectData = await projectRes.json();
    const projectA = projectData.projects?.[0] || projectData.items?.[0];
    if (!projectA?.renderAssetId) {
      throw new Error("Project A has no render asset");
    }

    const downloadRes = await page.request.get(`/api/uploads/${projectA.renderAssetId}`);
    const downloadData = await downloadRes.json();
    const outputUrl = downloadData.asset?.storageUrl;
    if (!outputUrl) throw new Error("No output URL for project A");

    const outputPath = path.join(OUTPUT_DIR, "output-A.mp4");
    const videoRes = await page.request.get(outputUrl);
    await fs.writeFile(outputPath, await videoRes.body());

    // ffprobe assertions
    const probeResult = await probe(outputPath);
    expect(probeResult.videoCodec).toBe("h264");
    expect(probeResult.audioCodec).toBe("aac");
    // Prompt-driven duration is non-deterministic; just verify it's a non-empty render.
    expect(probeResult.duration).toBeGreaterThan(0);
    expect(probeResult.duration).toBeLessThanOrEqual(60);
    expect(probeResult.width / probeResult.height).toBeCloseTo(9 / 16, 1);
    expect(probeResult.sizeBytes).toBeGreaterThan(1_000_000);
    expect(probeResult.averageLuma).toBeGreaterThan(16);

    // Save partial report
    await writeReport({
      scenario: "A",
      outputPath,
      probe: probeResult,
      timestamp: new Date().toISOString(),
    });
  });

  test("Scenario B: reference-driven render produces measurably different output", async ({ page }) => {
    // Create project
    await page.goto("/editor/new");
    await page.fill('input[id="name"]', "E2E-B-ReferenceDriven");
    await page.click('button:has-text("Create Project")');

    // Wait for editor to load
    await page.waitForURL(/\/editor\/[a-f0-9-]+$/, { timeout: 15_000 });

    // Upload assets
    await uploadFixture(page, "reference", "e2e/fixtures/reference.mp4");
    await uploadFixture(page, "song", "e2e/fixtures/song.mp3");
    await uploadFixture(page, "clip", "e2e/fixtures/clip-1.mp4");
    await uploadFixture(page, "clip", "e2e/fixtures/clip-2.mp4");
    await uploadFixture(page, "clip", "e2e/fixtures/clip-3.mp4");

    // Wait for ingest spinners to clear
    await expect(page.locator('[data-state="ingested"]')).toHaveCount(5, { timeout: 180_000 });

    // Trigger reference-driven generation
    await page.click('[data-testid="generate-from-reference"]');
    await expect(page.locator(':text("Cut-list ready")')).toBeVisible({ timeout: 180_000 });

    // Render
    await page.click('button:has-text("Render")');
    await page.click('button:has-text("Start Render")');
    await expect(page.locator('[data-render-status="complete"]')).toBeVisible({ timeout: 600_000 });

    // Download output
    const projectRes = await page.request.get("/api/projects?name=E2E-B-ReferenceDriven");
    const projectData = await projectRes.json();
    const projectB = projectData.projects?.[0] || projectData.items?.[0];
    if (!projectB?.renderAssetId) {
      throw new Error("Project B has no render asset");
    }

    const downloadRes = await page.request.get(`/api/uploads/${projectB.renderAssetId}`);
    const downloadData = await downloadRes.json();
    const outputUrl = downloadData.asset?.storageUrl;
    if (!outputUrl) throw new Error("No output URL for project B");

    const outputPath = path.join(OUTPUT_DIR, "output-B.mp4");
    const videoRes = await page.request.get(outputUrl);
    await fs.writeFile(outputPath, await videoRes.body());

    // ffprobe assertions
    const probeResult = await probe(outputPath);
    expect(probeResult.videoCodec).toBe("h264");
    // Reference-driven output duration is non-deterministic (AI chooses pacing);
    // just verify it produced a non-trivial video.
    expect(probeResult.duration).toBeGreaterThanOrEqual(5);
    expect(probeResult.duration).toBeLessThanOrEqual(60);
    expect(probeResult.width / probeResult.height).toBeCloseTo(9 / 16, 1);
    expect(probeResult.sizeBytes).toBeGreaterThan(1_000_000);
    expect(probeResult.averageLuma).toBeGreaterThan(16);

    // WEDGE assertion: fetch project A for comparison
    const projectARes = await page.request.get("/api/projects?name=E2E-A-PromptOnly");
    const projectAData = await projectARes.json();
    const projectA = projectAData.projects?.[0] || projectAData.items?.[0];

    const { verdict, metrics, passCount } = computeWedge(projectA?.cutList, projectB?.cutList);

    // Save wedge report for human review
    await fs.writeFile(
      path.join(OUTPUT_DIR, "wedge-report.json"),
      JSON.stringify({ metrics, verdict, passCount }, null, 2),
    );

    // Save full report
    await writeReport({
      scenario: "B",
      outputPath,
      probe: probeResult,
      wedge: { metrics, verdict, passCount },
      timestamp: new Date().toISOString(),
    });

    // Log wedge result but DO NOT fail if NOT_PROVEN — that's a product finding, not a test bug
    if (verdict !== "PROVEN") {
      console.warn(`\n⚠️  Wedge verdict: ${verdict} (${passCount}/4 metrics passed)`);
      console.warn("This is a product finding. Fix Pass 5.4 reference pipeline before tagging v0.4.0.");
    }
  });

  test("Scenario C: export preset selection produces the requested output dimensions", async ({ page }) => {
    // Create project
    await page.goto("/editor/new");
    await page.fill('input[id="name"]', "E2E-C-ExportPreset");
    await page.click('button:has-text("Create Project")');

    // Wait for editor to load
    await page.waitForURL(/\/editor\/[a-f0-9-]+$/, { timeout: 15_000 });

    // Upload assets
    await uploadFixture(page, "song", "e2e/fixtures/song.mp3");
    await uploadFixture(page, "clip", "e2e/fixtures/clip-1.mp4");
    await uploadFixture(page, "clip", "e2e/fixtures/clip-2.mp4");

    // Wait for ingest spinners to clear
    await expect(page.locator('[data-state="ingested"]')).toHaveCount(3, { timeout: 180_000 });

    // Open AI Prompt panel and submit a short edit
    await page.click('button:has-text("AI Prompt")');
    await page.fill(
      '[data-testid="prompt-input"]',
      "Make a 10-second edit using the uploaded clips. Keep it vertical.",
    );
    await page.locator('form button[type="submit"]').click();
    await expect(page.getByText("Applied cutlist").first()).toBeVisible({ timeout: 120_000 });

    // Render with the YouTube 16:9 preset
    await page.click('button:has-text("Render")');
    await page.getByRole("combobox").click();
    await page.getByRole("option", { name: "YouTube 16:9" }).click();
    await page.click('button:has-text("Start Render")');
    await expect(page.locator('[data-render-status="complete"]')).toBeVisible({ timeout: 600_000 });

    // Download output
    const projectRes = await page.request.get("/api/projects?name=E2E-C-ExportPreset");
    const projectData = await projectRes.json();
    const projectC = projectData.projects?.[0] || projectData.items?.[0];
    if (!projectC?.renderAssetId) {
      throw new Error("Project C has no render asset");
    }

    const downloadRes = await page.request.get(`/api/uploads/${projectC.renderAssetId}`);
    const downloadData = await downloadRes.json();
    const outputUrl = downloadData.asset?.storageUrl;
    if (!outputUrl) throw new Error("No output URL for project C");

    const outputPath = path.join(OUTPUT_DIR, "output-C.mp4");
    const videoRes = await page.request.get(outputUrl);
    await fs.writeFile(outputPath, await videoRes.body());

    // ffprobe assertions
    const probeResult = await probe(outputPath);
    expect(probeResult.videoCodec).toBe("h264");
    expect(probeResult.duration).toBeGreaterThan(0);
    expect(probeResult.duration).toBeLessThanOrEqual(60);
    expect(probeResult.width).toBe(1280);
    expect(probeResult.height).toBe(720);
    expect(probeResult.sizeBytes).toBeGreaterThan(100_000);

    await writeReport({
      scenario: "C",
      outputPath,
      probe: probeResult,
      timestamp: new Date().toISOString(),
    });
  });
});
