/**
 * Spec V7 T8 — the post-call recap entry (chat-thread surface).
 *
 * Renders from the persisted lifecycle recap (real `call-recap` over jsdom
 * localStorage); the persistence rules are owned by `lib/voice/call-recap.test.ts`.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";
import messages from "@/i18n/messages/en.json";
import { loadRecap, saveRecap } from "@/lib/voice/call-recap";
import { CallRecap } from "./call-recap";

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

function renderRecap(conversationId: string) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <CallRecap conversationId={conversationId} />
    </NextIntlClientProvider>,
  );
}

afterEach(() => {
  window.localStorage.clear();
});

describe("CallRecap", () => {
  it("renders nothing when the conversation has no recap", () => {
    const { container } = renderRecap("c-1");
    expect(container.querySelector('[data-slot="call-recap"]')).toBeNull();
  });

  it("shows the call duration as a trace (no transcript link — that's V9)", async () => {
    saveRecap({
      conversationId: "c-1",
      personaName: "Ada",
      durationMs: 125_000,
      endedAt: 0,
    });
    renderRecap("c-1");
    await waitFor(() =>
      expect(screen.getByText(/Call ended · 2 min/)).toBeInTheDocument(),
    );
    // V7 ships the trace, not a transcript view (forward Seam B / V9) — so there
    // is no misleading "view transcript" link back into the same thread.
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("dismiss clears the recap", async () => {
    saveRecap({
      conversationId: "c-1",
      personaName: "Ada",
      durationMs: 30_000,
      endedAt: 0,
    });
    renderRecap("c-1");
    const dismiss = await screen.findByRole("button", { name: "Dismiss" });
    fireEvent.click(dismiss);
    expect(loadRecap("c-1")).toBeNull();
    expect(screen.queryByText(/Call ended/)).not.toBeInTheDocument();
  });
});
