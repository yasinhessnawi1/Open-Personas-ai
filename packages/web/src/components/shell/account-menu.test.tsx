/**
 * Spec 35 D-35-16 — the custom account menu's edition-degrade contract.
 *
 * The menu reads `useAccount()` from the `@/auth` façade (mocked here). Cloud
 * (available + sign-out) shows the name + a Sign-out action; community
 * (degraded) shows a fallback label + NO sign-out. The component imports no
 * `@clerk/*` itself — it's edition-agnostic.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Account } from "@/auth/types";
import { AccountMenu } from "./account-menu";

let account: Account;
vi.mock("@/auth", () => ({ useAccount: () => account }));
vi.mock("next-themes", () => ({ useTheme: () => ({ setTheme: vi.fn() }) }));

const messages = {
  nav: {
    settings: "Settings",
    account: {
      menu: "Account",
      manageAccount: "Manage account",
      appearance: "Appearance",
      signOut: "Sign out",
      plan: "Account",
    },
  },
  theme: { light: "Light", dark: "Dark", system: "System" },
};

function wrap(ui: React.ReactNode) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      {ui}
    </NextIntlClientProvider>,
  );
}

describe("AccountMenu", () => {
  beforeEach(() => {
    account = {
      name: "",
      email: null,
      imageUrl: null,
      available: false,
    };
  });

  it("cloud: shows the user name and a Sign-out action", () => {
    const signOut = vi.fn();
    account = {
      name: "Ada Lovelace",
      email: "ada@example.com",
      imageUrl: null,
      available: true,
      signOut,
      manageAccount: vi.fn(),
    };
    wrap(<AccountMenu />);
    expect(screen.getByText("Ada Lovelace")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Account" }));
    const signOutItem = screen.getByText("Sign out");
    fireEvent.click(signOutItem);
    expect(signOut).toHaveBeenCalled();
  });

  it("community: falls back to a label and shows NO sign-out", () => {
    wrap(<AccountMenu />);
    // No name → the menu trigger falls back to the "Account" label.
    expect(screen.getAllByText("Account").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Account" }));
    // Settings is always present; sign-out is cloud-only.
    expect(screen.getByText("Settings")).toBeTruthy();
    expect(screen.queryByText("Sign out")).toBeNull();
  });
});
