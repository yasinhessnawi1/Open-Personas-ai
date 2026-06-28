/**
 * N3 (MCP-as-apps) Task 5 — the persona-detail unavailable-apps tombstone.
 *
 * Verifies: renders a tombstone per name when the list is non-empty; renders
 * NOTHING when empty; carries no enable/re-add control (the server is gone —
 * informational only, N3-D-9).
 */

import { render } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";
import messages from "@/i18n/messages/en.json";
import { UnavailableApps } from "./unavailable-apps";

function renderWith(names: string[]) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <UnavailableApps names={names} />
    </NextIntlClientProvider>,
  );
}

describe("UnavailableApps", () => {
  it("renders a tombstone per removed app when the list is non-empty", () => {
    const { container } = renderWith(["github", "slack"]);
    expect(
      container.querySelector('[data-slot="persona-detail-unavailable-apps"]'),
    ).toBeTruthy();
    const items = container.querySelectorAll('[data-slot="unavailable-app"]');
    expect(items.length).toBe(2);
    expect(items[0].textContent).toContain("github");
    expect(items[0].textContent?.toLowerCase()).toContain("removed");
  });

  it("renders nothing when the list is empty (the common case)", () => {
    const { container } = renderWith([]);
    expect(container.firstChild).toBeNull();
  });

  it("carries no enable / re-add control (informational only — the server is gone)", () => {
    const { container } = renderWith(["github"]);
    expect(container.querySelector("button")).toBeNull();
    expect(container.querySelector('[data-slot="app-toggle"]')).toBeNull();
    expect(container.querySelector("input")).toBeNull();
  });
});
