/**
 * Spec V7 T4 — the end-and-switch confirm.
 *
 * Asserts: hidden when nothing pending; on confirm it ends+switches THEN
 * navigates to the new call; cancel dismisses without navigating.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";
import messages from "@/i18n/messages/en.json";
import type { CallSession, CallTarget } from "@/lib/voice/call-session-context";
import { SwitchCallDialog } from "./switch-call-dialog";

const h = vi.hoisted(() => ({
  session: null as Partial<CallSession> | null,
  push: vi.fn(),
}));

vi.mock("@/lib/voice/call-session-context", () => ({
  useCallSession: () => h.session,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: h.push }),
}));

const CURRENT: CallTarget = {
  personaId: "p-a",
  conversationId: "c-a",
  personaName: "Ada",
};
const NEXT: CallTarget = {
  personaId: "p-b",
  conversationId: "c-b",
  personaName: "Boole",
};

function renderDialog() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <SwitchCallDialog />
    </NextIntlClientProvider>,
  );
}

beforeEach(() => {
  h.push.mockReset();
});

describe("SwitchCallDialog", () => {
  it("renders nothing when no switch is pending", () => {
    h.session = { pendingSwitch: null, target: CURRENT };
    const { container } = renderDialog();
    expect(container.querySelector('[role="alertdialog"]')).toBeNull();
  });

  it("confirm ends+switches then navigates to the new call", async () => {
    const confirmSwitch = vi.fn(async () => undefined);
    h.session = {
      pendingSwitch: NEXT,
      target: CURRENT,
      confirmSwitch,
      cancelSwitch: vi.fn(),
    };
    renderDialog();
    expect(screen.getByRole("alertdialog")).toHaveAccessibleName(
      /Switch your call/,
    );
    fireEvent.click(screen.getByRole("button", { name: "End & switch" }));
    await waitFor(() => expect(confirmSwitch).toHaveBeenCalledTimes(1));
    expect(h.push).toHaveBeenCalledWith("/chat/c-b/voice");
  });

  it("cancel dismisses without navigating", () => {
    const cancelSwitch = vi.fn();
    h.session = {
      pendingSwitch: NEXT,
      target: CURRENT,
      confirmSwitch: vi.fn(),
      cancelSwitch,
    };
    renderDialog();
    fireEvent.click(screen.getByRole("button", { name: "Stay on call" }));
    expect(cancelSwitch).toHaveBeenCalledTimes(1);
    expect(h.push).not.toHaveBeenCalled();
  });
});
