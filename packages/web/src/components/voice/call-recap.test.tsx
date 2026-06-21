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

  it("shows the duration + a view-transcript link for a recorded call", async () => {
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
    expect(
      screen.getByRole("link", { name: "View transcript" }),
    ).toHaveAttribute("href", "/chat/c-1");
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
