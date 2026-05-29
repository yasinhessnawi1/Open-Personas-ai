import { defineConfig, devices } from "@playwright/test";
import dotenv from "dotenv";

// Load the local Clerk keys into the test runner's env (gitignored .env.local).
dotenv.config({ path: ".env.local" });
// @clerk/testing's clerkSetup reads CLERK_PUBLISHABLE_KEY; map Next's public name.
process.env.CLERK_PUBLISHABLE_KEY ||=
  process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  // The Clerk signup UI (auth.setup) is occasionally flaky (email-code prepare
  // race); one retry keeps the harness stable. The app code is deterministic.
  retries: 1,
  reporter: "list",
  timeout: 60_000,
  use: { baseURL: BASE_URL, trace: "retain-on-failure" },
  projects: [
    // 1. Fetch a Clerk Testing Token (bypasses bot detection).
    { name: "setup", testMatch: /global\.setup\.ts/ },
    // 2. Sign up a fresh +clerk_test user and save the authed storage state.
    { name: "auth", testMatch: /auth\.setup\.ts/, dependencies: ["setup"] },
    // 3. Page specs run authed (reuse the saved session).
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        storageState: "playwright/.clerk/user.json",
      },
      dependencies: ["auth"],
      testMatch: /.*\.spec\.ts/,
    },
  ],
  webServer: {
    command: "pnpm dev",
    url: BASE_URL,
    timeout: 120_000,
    reuseExistingServer: true,
    stdout: "ignore",
    stderr: "pipe",
  },
});
