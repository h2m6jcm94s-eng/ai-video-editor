import { expect, test } from "@playwright/test";
import { uploadFixture } from "../../helpers/upload";

const UPLOADS = [
  { type: "song" as const, file: "e2e/fixtures/song.mp3" },
  { type: "clip" as const, file: "e2e/fixtures/clip-1.mp4" },
  { type: "clip" as const, file: "e2e/fixtures/clip-2.mp4" },
  { type: "clip" as const, file: "e2e/fixtures/clip-3.mp4" },
];

async function createProjectViaApi(page: any, name: string) {
  const res = await page.request.post("/api/projects", {
    data: { name, styleTier: "with_effects", mode: "auto" },
  });
  if (!res.ok()) {
    const body = await res.text();
    throw new Error(`Project creation failed: ${res.status()} ${body}`);
  }
  const data = await res.json();
  return data.project.id as string;
}

test.describe("Smoke: asset upload and ingest", () => {
  test("uploads song and clips and reaches ingested state", async ({ page }) => {
    const projectId = await createProjectViaApi(page, "E2E Upload Smoke");
    await page.goto(`/editor/${projectId}`);
    await expect(page.locator("text=Upload Clip").first()).toBeVisible({ timeout: 10_000 });

    for (const { type, file } of UPLOADS) {
      await uploadFixture(page, type, file);
      const filename = file.split("/").pop()!;
      await expect(page.locator(`text=${filename}`).first()).toBeVisible({ timeout: 30_000 });
    }

    // All four assets should transition to ingested within 180s
    await expect(page.locator('[data-state="ingested"]')).toHaveCount(UPLOADS.length, { timeout: 180_000 });

    // No lingering error toasts from the upload flow
    const toasts = page.locator("[data-sonner-toast] [data-title]");
    const errorToasts = await toasts.filter({ hasText: /Upload failed|Upload error|Error/i }).count();
    expect(errorToasts).toBe(0);
  });

  test("uploads a reference video and reaches ingested state", async ({ page }) => {
    const projectId = await createProjectViaApi(page, "E2E Upload Reference Smoke");
    await page.goto(`/editor/${projectId}`);
    await expect(page.locator("text=Upload Clip").first()).toBeVisible({ timeout: 10_000 });

    await uploadFixture(page, "reference", "e2e/fixtures/reference.mp4");
    await expect(page.locator("text=reference.mp4").first()).toBeVisible({ timeout: 30_000 });
    await expect(page.locator('[data-state="ingested"]')).toHaveCount(1, { timeout: 180_000 });
  });
});
