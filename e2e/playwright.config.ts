import { defineConfig, devices } from "@playwright/test";
// Load .env.local (or .env) so E2E_TEST_USER_EMAIL/PASSWORD are available
import { config } from "dotenv";
import { existsSync } from "fs";
import path from "path";

config({
  path: existsSync("e2e/.env.e2e") ? "e2e/.env.e2e" : existsSync(".env.local") ? ".env.local" : ".env",
});

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
    // Guard against infinitely retrying actions on non-actionable or detached
    // elements. The 15-minute per-test timeout is still available for long
    // render/pipeline specs, but individual clicks/fills must resolve quickly.
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
  },
  projects: [
    { name: "setup", testMatch: /auth\.setup\.ts$/ },
    {
      name: "chromium",
      testIgnore: /auth\.setup\.ts$/,
      use: { ...devices["Desktop Chrome"], storageState: "e2e/.auth/user.json" },
      dependencies: ["setup"],
    },
    {
      name: "mobile-safari",
      testIgnore: /auth\.setup\.ts$/,
      use: { ...devices["iPhone 14"], storageState: "e2e/.auth/user.json" },
      dependencies: ["setup"],
    },
  ],
  webServer: {
    command: "pnpm dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      E2E: "1",
    },
  },
});
