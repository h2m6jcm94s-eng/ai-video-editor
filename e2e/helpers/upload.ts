import type { Page } from "@playwright/test";
import path from "path";

const FIXTURES_DIR = path.join(process.cwd(), "e2e", "fixtures");

export async function uploadFixture(
  page: Page,
  type: "reference" | "song" | "clip",
  relativePath: string,
): Promise<void> {
  const filePath = path.resolve(FIXTURES_DIR, path.basename(relativePath));
  const input = page.locator(`[data-testid="upload-${type}"]`).first();
  await input.setInputFiles(filePath);
}
