import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./tests", testMatch: "*.spec.ts", fullyParallel: false, workers: 1, timeout: 180_000,
  expect: { timeout: 20_000 }, retries: 0,
  use: { baseURL: process.env.PAXVEIL_WEB_URL || "http://127.0.0.1:3000", trace: "retain-on-failure", screenshot: "only-on-failure", channel: process.env.PLAYWRIGHT_CHANNEL || undefined },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  reporter: [["list"], ["html", { open: "never" }]]
});
