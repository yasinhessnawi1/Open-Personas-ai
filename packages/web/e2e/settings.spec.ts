import { expect, test } from "@playwright/test";

test("settings shows credits, usage, and a working tier-badge toggle", async ({
  page,
}) => {
  await page.goto("/settings");

  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible({
    timeout: 30_000,
  });

  // Credits + usage sections render (acceptance #7).
  await expect(page.getByRole("heading", { name: "Credits" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Usage" })).toBeVisible();

  // The tier-badge visibility toggle flips and persists locally.
  const toggle = page.getByRole("switch", { name: "Model tier badges" });
  await expect(toggle).toHaveAttribute("aria-checked", "true");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "false");
});

test("conversations list renders", async ({ page }) => {
  await page.goto("/conversations");
  await expect(
    page.getByRole("heading", { name: "Conversations" }),
  ).toBeVisible({ timeout: 30_000 });
});
