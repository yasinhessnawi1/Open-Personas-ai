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

test("chat streams a persona response with a tier badge", async ({ page }) => {
  await page.goto("/personas");
  const token = await clerkToken(page);
  const auth = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };

  // Seed a persona + a conversation via the API.
  const personaRes = await page.request.post(`${API}/v1/personas`, {
    headers: auth,
    data: { yaml: VALID_YAML },
  });
  expect(personaRes.status()).toBe(201);
  const personaId = (await personaRes.json()).id as string;

  const convRes = await page.request.post(
    `${API}/v1/personas/${personaId}/conversations`,
    {
      headers: auth,
      data: { title: "" },
    },
  );
  expect(convRes.status()).toBe(201);
  const conversationId = (await convRes.json()).id as string;

  // Open the chat; the identity header shows the persona.
  await page.goto(`/chat/${conversationId}`);
  await expect(page.getByText("Astrid").first()).toBeVisible();

  // Send a message → the user turn renders, then a streamed assistant turn.
  await page.getByRole("textbox").fill("Say hello in one short sentence.");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(
    page.getByText("Say hello in one short sentence."),
  ).toBeVisible();

  // The turn completes: a tier badge appears (only set on the `done` event).
  // Generous timeout for the live DeepSeek generation.
  await expect(page.locator('[title^="Model tier"]')).toBeVisible({
    timeout: 90_000,
  });
});
