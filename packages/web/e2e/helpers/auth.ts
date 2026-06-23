import type { Page } from "@playwright/test";

export const TEST_PASSWORD = "Persona-Test-1234!";

/** Where a completed sign-in / sign-up lands (the configured fallback target). */
export const POST_AUTH_URL = "**/personas";

/** A fresh Clerk test email. `+clerk_test` addresses accept the fixed OTP 424242. */
export function freshTestEmail(): string {
  return `persona+clerk_test_${Date.now()}@example.com`;
}

/** Enter the fixed `+clerk_test` OTP (424242) into the branded per-digit code input. */
async function enterTestOtp(page: Page): Promise<void> {
  const first = page.locator('input[aria-label="Digit 1"]');
  await first.waitFor({ timeout: 30_000 });
  // Let Clerk finish "preparing" (sending) the email code before entering it —
  // entering too early triggers "you need to send a verification code first".
  await page.waitForTimeout(2500);
  await first.click();
  // The OtpInput distributes sequential key presses across its six boxes and
  // auto-submits on the sixth, so type the code digit-by-digit.
  await page.keyboard.type("424242");
}

/**
 * Drive the branded custom sign-up flow (`sign-up.cloud.tsx`) to create a new
 * test user and land authenticated on `/personas`.
 *
 * Assumes `setupClerkTestingToken({ page })` has already run (bot-detection
 * bypass). Targets the custom flow's own field ids / button labels — NOT Clerk's
 * prebuilt `<SignUp/>` widget (which this app does not use). Returns the email.
 */
export async function signUpNewUser(page: Page): Promise<string> {
  const email = freshTestEmail();
  await page.goto("/sign-up");

  await page.locator("#su-email").waitFor({ timeout: 30_000 });
  await page.locator("#su-email").fill(email);
  await page.locator("#su-pw").fill(TEST_PASSWORD);
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();

  await enterTestOtp(page);

  // Landing on the configured post-auth target IS the "signed in" signal: the
  // route is protected by clerkMiddleware, so reaching it means the session is
  // active (an unauthenticated hit would have bounced to /sign-in).
  await page.waitForURL(POST_AUTH_URL, { timeout: 30_000 });
  return email;
}

/**
 * Drive the branded custom sign-in flow (`sign-in.cloud.tsx`) for an existing
 * user (email → password → submit) and land authenticated on `/personas`.
 */
export async function signInExistingUser(
  page: Page,
  email: string,
  password: string = TEST_PASSWORD,
): Promise<void> {
  await page.goto("/sign-in");
  await page.locator("#si-email").waitFor({ timeout: 30_000 });
  await page.locator("#si-email").fill(email);
  await page.getByRole("button", { name: "Continue", exact: true }).click();

  await page.locator("#si-pw").waitFor({ timeout: 30_000 });
  await page.locator("#si-pw").fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();

  await page.waitForURL(POST_AUTH_URL, { timeout: 30_000 });
}
