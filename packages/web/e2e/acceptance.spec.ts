import { setupClerkTestingToken } from "@clerk/testing/playwright";
import { expect, test } from "@playwright/test";
import {
  signInExistingUser,
  signUpNewUser,
  TEST_PASSWORD,
} from "./helpers/auth";

// Acceptance #6 — exercise the FULL flow unauthenticated (ignore the saved session).
test.use({ storageState: { cookies: [], origins: [] } });

test("acceptance #6: signup, signin, signout, protected-route redirect", async ({
  page,
}) => {
  await setupClerkTestingToken({ page });

  // Signed out → a protected route redirects to sign-in.
  await page.goto("/personas");
  await page.waitForURL("**/sign-in**", { timeout: 20_000 });

  // Sign up → land authenticated on /personas.
  const email = await signUpNewUser(page);
  await expect(page).toHaveURL(/\/personas/);

  // Sign out via the Clerk client (single-session mode — clearing cookies alone
  // leaves a residual client session). Fire-and-don't-await: signOut navigates
  // to afterSignOutUrl and destroys the evaluate context mid-await.
  await page.evaluate(() => {
    const clerk = (window as unknown as { Clerk?: { signOut: () => unknown } })
      .Clerk;
    void clerk?.signOut();
  });
  await page.waitForURL("**/sign-in**", { timeout: 20_000 });
  await page.waitForFunction(
    () =>
      !(window as unknown as { Clerk?: { session?: unknown } }).Clerk?.session,
    undefined,
    { timeout: 20_000 },
  );

  // Signed out again → protected route redirects.
  await page.goto("/personas");
  await page.waitForURL("**/sign-in**", { timeout: 20_000 });

  // Sign back in (branded email→password flow) → authenticated again.
  await setupClerkTestingToken({ page });
  await signInExistingUser(page, email, TEST_PASSWORD);
  await expect(page).toHaveURL(/\/personas/);
});
