import { defineConfig, devices } from "@playwright/test";
// Load .env.local so E2E_TEST_USER_EMAIL/PASSWORD are available
import { config } from "dotenv";
import path from "path";

config({ path: ".env.local" });

export default defineConfig({
  testDir: path.join(__dirname, "specs"),
  outputDir: path.join(__dirname, "reports"),
  fullyParallel: false, // Scenarios must run sequentially (shared test user)
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  timeout: 15 * 60 * 1000, // 15 min per test
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3000",
    trace: "on-first-retry",
    video: "on-first-retry",
    screenshot: "only-on-failure",
    headless: process.env.E2E_HEADED !== "1",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
