import { defineConfig } from "@playwright/test";

// Acceptance specs run against a running stack: FAKE_LLM=1 scripts/dev.sh
export default defineConfig({
  testDir: "tests/acceptance",
  timeout: 60_000,
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:3000",
    launchOptions: process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {},
    screenshot: "only-on-failure",
  },
  outputDir: "../reports/playwright",
});
