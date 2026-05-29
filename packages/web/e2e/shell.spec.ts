import { expect, test } from "@playwright/test";

// Runs authed (reuses the saved storageState from auth.setup).
test.describe("app shell", () => {
  test("desktop: sidebar nav navigates + theme toggle switches to dark", async ({
    page,
  }) => {
    await page.goto("/personas");

    const personasLink = page.getByRole("link", {
      name: "Personas",
      exact: true,
    });
    const conversationsLink = page.getByRole("link", {
      name: "Conversations",
      exact: true,
    });
    const settingsLink = page.getByRole("link", {
      name: "Settings",
      exact: true,
    });
    await expect(personasLink).toBeVisible();
    await expect(conversationsLink).toBeVisible();
    await expect(settingsLink).toBeVisible();

    await conversationsLink.click();
    await expect(page).toHaveURL(/\/conversations$/);

    // Theme toggle → Dark applies the `dark` class on <html>.
    await page.getByRole("button", { name: "Toggle theme" }).click();
    await page.getByRole("menuitem", { name: "Dark" }).click();
    await expect(page.locator("html")).toHaveClass(/dark/);
  });

  test("mobile (375px): sheet nav opens and navigates", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    await page.goto("/personas");

    // Desktop sidebar is hidden; open the mobile sheet.
    await page.getByRole("button", { name: "Open menu" }).click();
    const settingsLink = page.getByRole("link", {
      name: "Settings",
      exact: true,
    });
    await expect(settingsLink).toBeVisible();
    await settingsLink.click();
    await expect(page).toHaveURL(/\/settings$/);
  });
});
