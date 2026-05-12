const { defineConfig, devices } = require("@playwright/test");

/**
 * Playwright configuration for Amarktai App Builder.
 *
 * Runs against the production URL by default.
 * Set PLAYWRIGHT_BASE_URL to override (e.g. http://localhost:3000 for local dev).
 *
 * Note: These tests require a running application server.
 * In CI, they run only against the deployed production URL.
 * Use `npm run dev` or `docker compose up` locally before running.
 */
module.exports = defineConfig({
  testDir: "./src/__tests__/e2e",
  timeout: 30_000,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? [["list"], ["json", { outputFile: "playwright-results.json" }]] : "list",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "https://builder.amarktai.com",
    headless: true,
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "mobile-chrome",
      use: { ...devices["Pixel 5"] },
    },
  ],
});
