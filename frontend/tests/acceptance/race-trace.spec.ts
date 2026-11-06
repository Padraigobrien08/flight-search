import { expect, test } from "@playwright/test";

test("F18: trace lists search events and the race replays two planners", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("run-search").click();
  await expect(page.getByTestId("itinerary-card").first()).toBeVisible({ timeout: 30_000 });

  const trace = page.getByTestId("trace-panel");
  await expect(trace.getByTestId("trace-event-search").first()).toBeVisible();
  expect(await trace.locator("[data-testid^='trace-event-']").count()).toBeGreaterThan(
    await trace.getByTestId("trace-event-search").count(),
  ); // at least one cache_bound or prune event as well

  const race = page.getByTestId("race-panel");
  await race.getByTestId("race-replay").click();
  await expect(race.getByTestId("race-line")).toHaveCount(2, { timeout: 15_000 });
  await expect(race.getByTestId("race-live")).toBeVisible();
});
