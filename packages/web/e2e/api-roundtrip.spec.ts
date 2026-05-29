import { expect, test } from "@playwright/test";

// Proves D-09-2 end-to-end: a real Clerk JWT (template "persona-api") validates
// against the running API (RS256 + the dashboard PEM + the aud). Uses
// page.request (server-side fetch) so this isolates JWT verification from CORS.
const API = process.env.E2E_API_BASE_URL ?? "http://127.0.0.1:8000";

type ClerkWindow = {
  Clerk: {
    session: { getToken: (o: { template: string }) => Promise<string | null> };
  };
};

test("clerk token validates against the live API (round-trip)", async ({
  page,
}) => {
  await page.goto("/personas");
  // Clerk JS hydrates the session asynchronously — wait for it before getToken.
  await page.waitForFunction(
    () =>
      Boolean(
        (window as unknown as { Clerk?: { session?: unknown } }).Clerk?.session,
      ),
    null,
    { timeout: 20_000 },
  );
  const token = await page.evaluate(async () => {
    const clerk = (window as unknown as ClerkWindow).Clerk;
    return await clerk.session.getToken({ template: "persona-api" });
  });
  expect(token, "expected a persona-api template token").toBeTruthy();

  const res = await page.request.get(`${API}/v1/me/credits`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(res.status()).toBe(200);
  expect(typeof (await res.json()).balance).toBe("number");
});
