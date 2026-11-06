import { expect, test } from "@playwright/test";

test("F16: form-first search shows ranked trade-off cards", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("trip-form")).toBeVisible();
  for (const id of ["depart-date", "flex-days", "search-budget", "pref-text", "run-search"]) {
    await expect(page.getByTestId(id)).toBeVisible();
  }
  await expect(page.getByTestId(/^pref-slider-/).first()).toBeVisible();

  await page.getByTestId("run-search").click();
  const cards = page.getByTestId("itinerary-card");
  await expect(cards.first()).toBeVisible({ timeout: 30_000 });
  expect(await cards.count()).toBeGreaterThan(1);
  // Each card states its total and how it compares with the cheapest.
  await expect(cards.first().getByTestId("card-total")).toContainText("£");
  await expect(cards.first().getByTestId("card-vs-cheapest")).toBeVisible();
});
