import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  workers: process.env.CI ? 2 : 4,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:1420",
    channel: process.env.CI ? undefined : "chrome",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev",
    url: "http://127.0.0.1:1420",
    reuseExistingServer: !process.env.CI,
  },
  outputDir: "test-results",
});
