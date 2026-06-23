import { setupClerkTestingToken } from "@clerk/testing/playwright";
import { expect, test } from "@playwright/test";
import {
  signInExistingUser,
  signUpNewUser,
  TEST_PASSWORD,
} from "./helpers/auth";

/**
 * Auth-flow regression suite (fix/auth-flows).
 *
 * Locks the three Clerk auth bugs that shipped broken in the custom branded
 * flows (sign-in.cloud.tsx / sign-up.cloud.tsx) so they cannot silently
 * regress:
 *
 *   bug 1 — an already-signed-in visitor to /sign-in or /sign-up must be
 *           redirected to the app, NOT shown a form that 400s with
 *           `session_exists` ("You're already signed in.").
 *   bug 2 — a completed sign-in must land on the configured fallback target
 *           (/personas), not the bare "/".
 *   bug 3 — a completed sign-up (email-code verify) must land on the configured
 *           fallback target (/personas), not the bare "/".
 *
 * These run unauthenticated (own session), independent of the saved storage
 * state, since they manage sign-in / sign-out themselves.
 */
test.use({ storageState: { cookies: [], origins: [] } });

test.describe("auth flows", () => {
  test("bug 3: sign-up lands on the configured app target (/personas)", async ({
    page,
  }) => {
    await setupClerkTestingToken({ page });
    // signUpNewUser asserts it reaches **/personas; an explicit URL check makes
    // the regression intent obvious at the call site.
    await signUpNewUser(page);
    await expect(page).toHaveURL(/\/personas/);
  });

  test("bug 2: sign-in lands on the configured app target (/personas)", async ({
    page,
  }) => {
    await setupClerkTestingToken({ page });
    const email = await signUpNewUser(page);

    // Sign out via the Clerk client itself. The app runs single-session mode, so
    // a residual client session makes the next signIn.create() fail with
    // `single_session_mode`; clearing cookies alone does not tear the client
    // session down. Wait until the client reports signed-out before continuing.
    // Fire signOut without awaiting it inside the page: signOut navigates to
    // afterSignOutUrl (/sign-in), which destroys the evaluate execution context
    // mid-await and would reject. Trigger it, then wait for the resulting
    // navigation + the client to report signed-out from the test side.
    await page.evaluate(() => {
      const clerk = (
        window as unknown as { Clerk?: { signOut: () => unknown } }
      ).Clerk;
      void clerk?.signOut();
    });
    await page.waitForURL("**/sign-in**", { timeout: 20_000 });
    await page.waitForFunction(
      () =>
        !(window as unknown as { Clerk?: { session?: unknown } }).Clerk
          ?.session,
      undefined,
      { timeout: 20_000 },
    );
    // A fresh testing token is needed for the bot-protected sign-in.
    await setupClerkTestingToken({ page });

    // Fresh sign-in through the branded email→password flow.
    await signInExistingUser(page, email, TEST_PASSWORD);
    await expect(page).toHaveURL(/\/personas/);
  });

  test("bug 1: an already-signed-in visit to /sign-in redirects to the app", async ({
    page,
  }) => {
    await setupClerkTestingToken({ page });
    await signUpNewUser(page); // now has an active session

    // Land on the auth page WITH a live session — must bounce to the app, never
    // render the form (which would 400 with session_exists on submit).
    await page.goto("/sign-in");
    await page.waitForURL(/\/personas/, { timeout: 20_000 });
    await expect(page).toHaveURL(/\/personas/);
    // The sign-in form must not be present.
    await expect(page.locator("#si-email")).toHaveCount(0);
  });

  test("bug 1: an already-signed-in visit to /sign-up redirects to the app", async ({
    page,
  }) => {
    await setupClerkTestingToken({ page });
    await signUpNewUser(page); // now has an active session

    await page.goto("/sign-up");
    await page.waitForURL(/\/personas/, { timeout: 20_000 });
    await expect(page).toHaveURL(/\/personas/);
    await expect(page.locator("#su-email")).toHaveCount(0);
  });
});
