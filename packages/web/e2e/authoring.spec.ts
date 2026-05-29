import { expect, test } from "@playwright/test";

// The marquee authoring flow (acceptance #3 + part of #1): NL → live frontier
// author → structured form → edit → form↔YAML sync → save → persisted + shown.
test("author a persona, edit it, sync YAML, and save", async ({ page }) => {
  await page.goto("/personas/new");
  await expect(
    page.getByRole("heading", { name: "Describe your persona" }),
  ).toBeVisible({ timeout: 30_000 });

  await page
    .getByRole("textbox")
    .fill(
      "A concise assistant who answers briefly and never gives legal advice.",
    );
  await page.getByRole("button", { name: "Generate persona" }).click();

  // The loading state reads as deliberate work (not a blank spinner).
  await expect(page.getByText("Authoring your persona")).toBeVisible({
    timeout: 15_000,
  });

  // The frontier author returns and the structured form populates (live DeepSeek).
  await expect(
    page.getByRole("heading", { name: "Review your persona" }),
  ).toBeVisible({ timeout: 120_000 });
  const nameInput = page.getByLabel("Name");
  await expect(nameInput).not.toHaveValue("");

  // Edit a field → toggle raw YAML → Monaco lazy-loads and reflects the edit.
  await nameInput.fill("E2E Edited Persona");
  await page.getByRole("button", { name: "Edit raw YAML" }).click();
  await expect(page.locator(".monaco-editor")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".monaco-editor")).toContainText(
    "E2E Edited Persona",
    { timeout: 15_000 },
  );

  // Save → redirect to the persona detail showing the edited identity.
  await page.getByRole("button", { name: "Save persona" }).click();
  await expect(
    page.getByRole("heading", { name: "E2E Edited Persona", exact: true }),
  ).toBeVisible({ timeout: 30_000 });
});
