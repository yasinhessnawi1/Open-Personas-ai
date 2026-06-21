/**
 * Spec V7 T6 — active-call indicator.
 *
 * Shows ONLY for the persona currently on a call, and is itself the one-tap
 * return-to-call link. Hidden for any other persona or when no call is active.
 */

import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";
import messages from "@/i18n/messages/en.json";
import type { CallSession, CallTarget } from "@/lib/voice/call-session-context";
import { ActiveCallIndicator } from "./active-call-indicator";

const h = vi.hoisted(() => ({ session: null as Partial<CallSession> | null }));

vi.mock("@/lib/voice/call-session-context", () => ({
  useCallSession: () => h.session,
}));
vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: React.ReactNode;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const TARGET: CallTarget = {
  personaId: "p-1",
  conversationId: "c-1",
  personaName: "Ada",
};

function renderFor(personaId: string) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ActiveCallIndicator personaId={personaId} />
    </NextIntlClientProvider>,
  );
}

describe("ActiveCallIndicator", () => {
  it("renders nothing when no call is active", () => {
    h.session = { isActive: false, target: null };
    const { container } = renderFor("p-1");
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing for a persona who is not the one on the call", () => {
    h.session = { isActive: true, target: TARGET };
    const { container } = renderFor("p-2");
    expect(container.firstChild).toBeNull();
  });

  it("shows a return-to-call link for the on-call persona", () => {
    h.session = { isActive: true, target: TARGET };
    renderFor("p-1");
    const link = screen.getByRole("link", {
      name: "Return to your call with Ada",
    });
    expect(link).toHaveAttribute("href", "/chat/c-1/voice");
  });
});
