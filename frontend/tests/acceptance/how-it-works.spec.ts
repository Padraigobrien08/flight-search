import { expect, test } from "@playwright/test";

test("F19: how-it-works page explains the system and shows the benchmark", async ({ page }) => {
  await page.goto("/how-it-works");
  for (const name of ["Architecture", "Fare models", "Benchmark"]) {
    await expect(page.getByRole("heading", { name })).toBeVisible();
  }
  await expect(page.getByTestId("ablation-table")).toBeVisible();
  await expect(page.getByTestId("regret-chart")).toBeVisible();
});
