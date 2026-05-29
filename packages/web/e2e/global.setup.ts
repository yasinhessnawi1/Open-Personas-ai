import { clerkSetup } from "@clerk/testing/playwright";
import { test as setup } from "@playwright/test";

// Fetches a Clerk Testing Token from the dev instance (using the keys loaded by
// playwright.config.ts) so subsequent navigations bypass bot detection.
setup("clerk setup", async () => {
  await clerkSetup();
});
