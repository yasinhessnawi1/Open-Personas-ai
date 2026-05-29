import { clerk, setupClerkTestingToken } from "@clerk/testing/playwright";
import { expect, test } from "@playwright/test";
import { signUpNewUser, TEST_PASSWORD } from "./helpers/auth";

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

  // Sign out → protected route redirects again.
  await clerk.signOut({ page });
  await page.goto("/personas");
  await page.waitForURL("**/sign-in**", { timeout: 20_000 });

  // Sign back in (password) → authenticated again.
  await clerk.signIn({
    page,
    signInParams: {
      strategy: "password",
      identifier: email,
      password: TEST_PASSWORD,
    },
  });
  await page.goto("/personas");
  await expect(page).toHaveURL(/\/personas/);
});
