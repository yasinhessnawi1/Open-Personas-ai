/**
 * Spec V7 T4 — the "Talk to {persona}" entry control.
 *
 * Asserts the one-click intent → navigation rule: navigate when the call starts
 * or is already current; DON'T navigate when a switch confirm is pending (the
 * dialog navigates on confirm).
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";
import messages from "@/i18n/messages/en.json";
import { CallControl } from "./call-control";

const h = vi.hoisted(() => ({
  requestCall: vi.fn(),
  push: vi.fn(),
}));

vi.mock("@/lib/voice/call-session-context", () => ({
  useCallSession: () => ({ requestCall: h.requestCall }),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: h.push }),
}));

function renderControl() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <CallControl persona={{ id: "p1", name: "Astrid" }} conversationId="c1" />
    </NextIntlClientProvider>,
  );
}

beforeEach(() => {
  h.requestCall.mockReset();
  h.push.mockReset();
});

describe("CallControl", () => {
  it("starting/current → requests the call and navigates to the full view", () => {
    h.requestCall.mockReturnValue("started");
    renderControl();
    fireEvent.click(screen.getByRole("button", { name: /Talk to Astrid/ }));
    expect(h.requestCall).toHaveBeenCalledWith(
      expect.objectContaining({ personaId: "p1", conversationId: "c1" }),
    );
    expect(h.push).toHaveBeenCalledWith("/chat/c1/voice");
  });

  it("switch pending → does NOT navigate (the confirm dialog will)", () => {
    h.requestCall.mockReturnValue("switch");
    renderControl();
    fireEvent.click(screen.getByRole("button", { name: /Talk to Astrid/ }));
    expect(h.push).not.toHaveBeenCalled();
  });
});
