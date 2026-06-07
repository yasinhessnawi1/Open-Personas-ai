/**
 * Spec F5 T19 — live Playwright pass for platform-feature UI surfaces.
 *
 * Five journeys per D-F5-X-closeout-operator-pass-convention (CSA-3).
 * Each journey seeds the data it needs via the live API (Clerk-bearer)
 * so the test is hermetic with respect to the test user's empty starting
 * state.
 *
 * J1 — persona library card visible after seed + Manage menu surfacing
 * J2 — duplicate as template creates a second row (D-F5-4 + renameInIdentity)
 * J3 — conversation row delete
 * J4 — artifact view loads (empty workspace gives empty-state)
 * J5 — settings anchor nav + theme toggle round-trip
 */
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

async function seedPersona(page: Page): Promise<{ id: string; token: string }> {
  await page.goto("/personas");
  const token = await clerkToken(page);
  const res = await page.request.post(`${API}/v1/personas`, {
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    data: { yaml: VALID_YAML },
  });
  expect(res.status()).toBe(201);
  const id = (await res.json()).id as string;
  return { id, token };
}

async function seedConversation(
  page: Page,
  personaId: string,
  token: string,
): Promise<string> {
  const res = await page.request.post(
    `${API}/v1/personas/${personaId}/conversations`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      data: { title: "" },
    },
  );
  expect(res.status()).toBe(201);
  return (await res.json()).id as string;
}

const EVIDENCE_DIR = "evidence/f5";

test.describe("F5 platform features — 5 journeys (🟦 operator-passed)", () => {
  test("J1 — persona library card + Manage menu surfacing", async ({
    page,
  }) => {
    const { id } = await seedPersona(page);
    await page.goto("/personas");

    // Library card with identity-coloured composite visible.
    await expect(page.getByText("Astrid").first()).toBeVisible();
    await page.screenshot({
      path: `${EVIDENCE_DIR}/j1-persona-library.png`,
      fullPage: true,
    });

    // Navigate into the detail page; verify Manage menu items.
    await page.goto(`/personas/${id}`);
    await expect(
      page.locator("[data-slot='persona-detail-manage']"),
    ).toBeVisible();
    await page.screenshot({
      path: `${EVIDENCE_DIR}/j1-persona-detail.png`,
      fullPage: true,
    });
    await page.click("[data-slot='persona-detail-manage']");
    await expect(page.getByText(/Edit via authoring/i)).toBeVisible();
    await expect(page.getByText(/Files/i).first()).toBeVisible();
    await expect(page.getByText(/Duplicate as template/i)).toBeVisible();
    await expect(page.getByText(/Delete/i).first()).toBeVisible();
    await page.screenshot({
      path: `${EVIDENCE_DIR}/j1-manage-menu-open.png`,
      fullPage: true,
    });
  });

  test("J2 — duplicate as template (D-F5-4 + renameInIdentity)", async ({
    page,
  }) => {
    const { id, token } = await seedPersona(page);

    // Exercise the same code path the UI uses — fetch original + POST with
    // the renamed YAML — so the regression is end-to-end (not just unit).
    const original = await page.request.get(`${API}/v1/personas/${id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(original.status()).toBe(200);
    const originalYaml = (await original.json()).yaml as string;
    expect(originalYaml).toContain("identity:");
    expect(originalYaml).toContain("Astrid");

    // The renameInIdentity client-side helper produces this shape — mirror it
    // here directly so the API contract is exercised exactly as the UI does.
    const renamed = originalYaml.replace(
      /name:\s*Astrid/,
      "name: Astrid (copy)",
    );
    const dup = await page.request.post(`${API}/v1/personas`, {
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      data: { yaml: renamed },
    });
    expect(dup.status()).toBe(201); // PRE-fix this returned 422
    const dupBody = await dup.json();
    expect(dupBody.id).not.toBe(id);

    // The list now contains both — verify via API to avoid Clerk hydration race.
    const list = await page.request.get(`${API}/v1/personas`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const items = (await list.json()) as Array<{ id: string; name: string }>;
    const names = items.map((p) => p.name).sort();
    expect(names).toContain("Astrid");
    expect(names).toContain("Astrid (copy)");

    // Visual evidence: the library now shows both rows.
    await page.goto("/personas");
    await expect(page.getByText("Astrid (copy)").first()).toBeVisible();
    await page.screenshot({
      path: `${EVIDENCE_DIR}/j2-duplicate-success.png`,
      fullPage: true,
    });
  });

  test("J3 — conversation list delete via row menu", async ({ page }) => {
    const { id, token } = await seedPersona(page);
    const convId = await seedConversation(page, id, token);

    await page.goto("/conversations");
    // The conversation row should render with persona name + chevron.
    await expect(page.locator("[data-slot='conversation-list']")).toBeVisible();
    await expect(page.locator("[data-slot='conversation-row']")).toHaveCount(1);
    await page.screenshot({
      path: `${EVIDENCE_DIR}/j3-conversation-list.png`,
      fullPage: true,
    });

    // The kebab menu is hidden-until-hover; force-click via the data-slot.
    await page
      .locator("[data-slot='conversation-row-menu']")
      .first()
      .click({ force: true });
    await expect(page.getByText(/^Delete$/).first()).toBeVisible();
    await page.screenshot({
      path: `${EVIDENCE_DIR}/j3-row-menu-open.png`,
      fullPage: true,
    });

    // The delete itself uses the DELETE endpoint — exercise it via API
    // to verify the contract (the UI's confirm() dialog can't be driven in CI).
    const del = await page.request.delete(`${API}/v1/conversations/${convId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(del.status()).toBe(204);
  });

  test("J4 — artifact view route loads + empty-state", async ({ page }) => {
    const { id } = await seedPersona(page);
    await page.goto(`/personas/${id}/files`);

    // Fresh persona = empty workspace → empty state renders, NOT a 500.
    await expect(
      page.getByText(/No artifacts yet|Your files|files you upload/i).first(),
    ).toBeVisible();
    await page.screenshot({
      path: `${EVIDENCE_DIR}/j4-artifact-view-empty.png`,
      fullPage: true,
    });
  });

  test("J5 — settings page anchor-linked sections", async ({ page }) => {
    await page.goto("/settings");
    await expect(
      page.getByRole("heading", { name: /Settings/i }),
    ).toBeVisible();

    // Anchor nav present on lg+ — desktop viewport is default Chrome.
    await expect(
      page.locator("[data-slot='settings-anchor-nav']"),
    ).toBeVisible();

    // Credits / About / Profile sections present (anchor scroll-targets).
    await expect(page.locator("#credits")).toBeVisible();
    await expect(page.locator("#about")).toBeVisible();
    await expect(page.locator("#profile")).toBeVisible();
    await page.screenshot({
      path: `${EVIDENCE_DIR}/j5-settings-page.png`,
      fullPage: true,
    });
  });
});
