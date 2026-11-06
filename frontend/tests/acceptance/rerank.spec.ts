import { expect, test } from "@playwright/test";

test("F17: moving a slider re-ranks without a new search", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("run-search").click();
  const cards = page.getByTestId("itinerary-card");
  await expect(cards.first()).toBeVisible({ timeout: 30_000 });

  const utilities = () => cards.evaluateAll((els) => els.map((e) => e.getAttribute("data-utility")));
  const before = await utilities();
  const paths: string[] = [];
  page.on("request", (r) => paths.push(new URL(r.url()).pathname));

  const slider = page.getByTestId("pref-slider-stopover_bonus");
  await slider.focus();
  await page.keyboard.press("End");

  await expect.poll(utilities, { timeout: 10_000 }).not.toEqual(before);
  expect(paths).toContain("/api/rerank");
  expect(paths).not.toContain("/api/plan");
});
