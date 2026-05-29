import { expect, type Page } from "@playwright/test";

export const TEST_PASSWORD = "Persona-Test-1234!";

/** A fresh Clerk test email. `+clerk_test` addresses accept the fixed OTP 424242. */
export function freshTestEmail(): string {
  return `persona+clerk_test_${Date.now()}@example.com`;
}

/**
 * Drive Clerk's <SignUp/> UI to create a new test user and land authenticated.
 * Assumes `setupClerkTestingToken({ page })` has already run (bot-detection bypass).
 * Returns the email used.
 */
export async function signUpNewUser(page: Page): Promise<string> {
  const email = freshTestEmail();
  await page.goto("/sign-up");

  await page.locator('input[name="emailAddress"]').waitFor({ timeout: 30_000 });
  await page.locator('input[name="emailAddress"]').fill(email);
  await page.locator('input[name="password"]').fill(TEST_PASSWORD);
  await page.getByRole("button", { name: "Continue", exact: true }).click();

  // Email-code verification — clerk_test → 424242.
  const otp = page
    .locator('input[autocomplete="one-time-code"], input[inputmode="numeric"]')
    .first();
  await otp.waitFor({ timeout: 30_000 });
  // Let Clerk finish "preparing" (sending) the email code before entering it —
  // entering too early triggers "you need to send a verification code first".
  await page.waitForTimeout(2500);
  await otp.fill("424242");

  // A complete code usually auto-submits; click Continue if it's still shown.
  const continueBtn = page.getByRole("button", {
    name: "Continue",
    exact: true,
  });
  if (await continueBtn.isVisible().catch(() => false)) {
    await continueBtn.click().catch(() => {});
  }

  await page.waitForURL("**/personas", { timeout: 30_000 });
  // The Clerk UserButton is the authoritative "signed in" signal.
  await expect(
    page.getByRole("button", { name: /open user menu/i }),
  ).toBeVisible();
  return email;
}
