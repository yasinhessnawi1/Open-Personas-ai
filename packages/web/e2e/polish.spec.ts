import { expect, type Page, test } from "@playwright/test";

const API = process.env.E2E_API_BASE_URL ?? "http://127.0.0.1:8000";

const VALID_YAML = `schema_version: "1.0"
identity:
  name: Polly
  role: Layout test persona
  background: |
    Exists to exercise responsive layouts.
  language_default: en
  constraints:
    - Keep it tidy.
self_facts:
  - fact: Lives in a 375px viewport.
    confidence: 1.0
worldview:
  - claim: No element should cause a horizontal scrollbar on mobile.
    domain: ux
    epistemic: belief
    confidence: 0.99
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

async function noHorizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
}

test("no horizontal overflow at 375px across the app (acceptance #5)", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/personas");
  const token = await clerkToken(page);
  const auth = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };

  const persona = await page.request.post(`${API}/v1/personas`, {
    headers: auth,
    data: { yaml: VALID_YAML },
  });
  expect(persona.status()).toBe(201);
  const personaId = (await persona.json()).id as string;

  const conv = await page.request.post(
    `${API}/v1/personas/${personaId}/conversations`,
    { headers: auth, data: { title: "" } },
  );
  const conversationId = (await conv.json()).id as string;

  const run = await page.request.post(`${API}/v1/personas/${personaId}/runs`, {
    headers: auth,
    data: { task: "A short task for the layout test." },
  });
  const runId = (await run.json()).id as string;

  const paths = [
    "/",
    "/personas",
    "/personas/new",
    `/personas/${personaId}`,
    `/personas/${personaId}/edit`,
    "/conversations",
    "/settings",
    `/chat/${conversationId}`,
    `/runs/${runId}`,
  ];

  for (const path of paths) {
    await page.goto(path);
    await page.waitForLoadState("load");
    await page.waitForTimeout(700); // let layout + first-compile settle
    const overflow = await noHorizontalOverflow(page);
    expect(overflow, `horizontal overflow on ${path}`).toBeLessThanOrEqual(1);
  }
});

test("pseudo-locale switches every string (acceptance #9)", async ({
  page,
  context,
}) => {
  await context.addCookies([
    {
      name: "NEXT_LOCALE",
      value: "xx",
      url: "http://localhost:3000",
    },
  ]);
  await page.goto("/personas");
  // Every string flows through t(): the pseudo-locale wraps each in «…».
  await expect(page.locator("text=«").first()).toBeVisible({ timeout: 30_000 });
});

test("chat page never loads Monaco (acceptance #10 bundle isolation)", async ({
  page,
}) => {
  await page.goto("/personas");
  const token = await clerkToken(page);
  const auth = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
  const persona = await page.request.post(`${API}/v1/personas`, {
    headers: auth,
    data: { yaml: VALID_YAML },
  });
  const personaId = (await persona.json()).id as string;
  const conv = await page.request.post(
    `${API}/v1/personas/${personaId}/conversations`,
    { headers: auth, data: { title: "" } },
  );
  const conversationId = (await conv.json()).id as string;

  const monacoRequests: string[] = [];
  page.on("request", (req) => {
    if (req.url().includes("monaco")) monacoRequests.push(req.url());
  });

  await page.goto(`/chat/${conversationId}`);
  await page.waitForLoadState("load");
  await page.waitForTimeout(1000);

  expect(monacoRequests, "Monaco must not load on the chat page").toEqual([]);
  await expect(page.locator(".monaco-editor")).toHaveCount(0);
});

test("dark mode applies via tokens", async ({ browser }) => {
  const ctx = await browser.newContext({
    colorScheme: "dark",
    storageState: "playwright/.clerk/user.json",
  });
  const page = await ctx.newPage();
  await page.goto("/");
  await expect(page.locator("html.dark")).toHaveCount(1, { timeout: 15_000 });
  await ctx.close();
});
