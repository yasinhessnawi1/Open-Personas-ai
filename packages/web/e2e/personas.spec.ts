import { expect, type Page, test } from "@playwright/test";

const API = process.env.E2E_API_BASE_URL ?? "http://127.0.0.1:8000";

const VALID_YAML = `schema_version: "1.0"
identity:
  name: Astrid
  role: Norwegian tenancy law assistant
  background: |
    Helps tenants understand husleieloven.
  language_default: en
  constraints:
    - Never give binding legal advice.
self_facts:
  - fact: Specialised in Norwegian residential tenancy.
    confidence: 1.0
worldview:
  - claim: Tenants in Norway have strong protections.
    domain: tenancy
    epistemic: fact
    confidence: 0.95
    valid_time: always
`;

type ClerkWindow = {
  Clerk: {
    session: { getToken: (o: { template: string }) => Promise<string | null> };
  };
};

async function clerkToken(page: Page): Promise<string> {
  await page.waitForFunction(
    () =>
      Boolean(
        (window as unknown as { Clerk?: { session?: unknown } }).Clerk?.session,
      ),
    null,
    { timeout: 20_000 },
  );
  const token = await page.evaluate(() =>
    (window as unknown as ClerkWindow).Clerk.session.getToken({
      template: "persona-api",
    }),
  );
  if (!token) throw new Error("no persona-api token");
  return token;
}

test("persona list (empty → seeded) + detail render", async ({ page }) => {
  await page.goto("/personas");

  // The empty state renders when the list is genuinely empty. In the shared-user
  // E2E suite other specs may already have seeded personas, so only assert it
  // when present (the seed → list → detail flow below is the order-independent
  // coverage).
  const emptyState = page.getByText("No personas yet");
  if (await emptyState.isVisible().catch(() => false)) {
    await expect(emptyState).toBeVisible();
  }

  // Seed one via the API (server-to-server create with the Clerk token).
  const token = await clerkToken(page);
  const created = await page.request.post(`${API}/v1/personas`, {
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    data: { yaml: VALID_YAML },
  });
  expect(created.status()).toBe(201);

  // The list now shows the persona card.
  await page.goto("/personas");
  await expect(page.getByText("Astrid").first()).toBeVisible();
  await expect(
    page.getByText("Norwegian tenancy law assistant").first(),
  ).toBeVisible();

  // Detail surfaces identity + a constraint. (waitForURL has a generous timeout:
  // the first navigation to /personas/[id] triggers a dev Turbopack compile.)
  await page
    .getByRole("link", { name: /Astrid/ })
    .first()
    .click();
  await page.waitForURL(/\/personas\/[^/]+$/, { timeout: 30_000 });
  // exact: the T07 detail page adds a "Give Astrid a task" h2 alongside the h1.
  await expect(
    page.getByRole("heading", { name: "Astrid", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Never give binding legal advice."),
  ).toBeVisible();
});
