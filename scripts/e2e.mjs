// Drive the real UI and save screenshots. Usage: node scripts/e2e.mjs [outDir] [prompt]
// Needs backend on :8000 and frontend on :3000 (FAKE_LLM=1 scripts/dev.sh).
import { mkdirSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(`${process.cwd()}/frontend/package.json`);
let chromium;
try {
  ({ chromium } = require("playwright"));
} catch {
  console.error("playwright missing: cd frontend && pnpm add -D playwright && pnpm exec playwright install chromium");
  process.exit(1);
}

const out = process.argv[2] ?? "reports/screens";
const prompt = process.argv[3] ?? "Edinburgh to Lima, out around 21–24 May 2027, home from La Paz the week of 6 June";
mkdirSync(out, { recursive: true });

const browser = await chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {});
const errors = [];
for (const [name, viewport] of [["desktop", { width: 1200, height: 900 }], ["mobile", { width: 390, height: 844 }]]) {
  const page = await browser.newPage({ viewport });
  page.on("pageerror", (e) => errors.push(`${name}: ${e.message}`));
  page.on("console", (m) => m.type() === "error" && errors.push(`${name} console: ${m.text()}`));
  await page.goto("http://localhost:3000");
  await page.screenshot({ path: `${out}/${name}-empty.png` });
  await page.getByRole("textbox").fill(prompt);
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.querySelectorAll("[class*='rounded-xl'][class*='border']").length > 0, null, { timeout: 30000 });
  await page.waitForTimeout(1000);
  await page.screenshot({ fullPage: true, path: `${out}/${name}-results.png` });
  await page.close();
}
await browser.close();
console.log(JSON.stringify({ errors, screenshots: out }));
process.exit(errors.length ? 2 : 0);
