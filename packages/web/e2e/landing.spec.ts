import { expect, test } from "@playwright/test";

test("landing page renders and routes into the app", async ({ page }) => {
  await page.goto("/");

  await expect(
    page.getByRole("heading", {
      name: "AI personas with a memory you can read.",
    }),
  ).toBeVisible({ timeout: 30_000 });

  // The four feature beats are present.
  await expect(
    page.getByRole("heading", { name: "Identity is data" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Tier-routed" }),
  ).toBeVisible();

  // The CTA routes into the app (the test session is signed in → "Open Persona").
  await page.getByRole("link", { name: "Open Persona" }).first().click();
  await expect(page).toHaveURL(/\/personas/);
});
