import { setupClerkTestingToken } from "@clerk/testing/playwright";
import { test as setup } from "@playwright/test";
import { signUpNewUser } from "./helpers/auth";

const authFile = "playwright/.clerk/user.json";

// Create a fresh authed session once per run and persist it; page specs reuse it.
setup("create authed session", async ({ page }) => {
  await setupClerkTestingToken({ page });
  await signUpNewUser(page);
  await page.context().storageState({ path: authFile });
});
