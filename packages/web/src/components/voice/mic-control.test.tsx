/**
 * Spec V7 T7 — mic input controls.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";
import messages from "@/i18n/messages/en.json";
import { INITIAL_CALL_STATE } from "@/lib/voice/call-state";
import { InputModeToggle, MicControl } from "./mic-control";

const h = vi.hoisted(() => ({
  inputMode: "always" as "always" | "ptt",
  pttHeld: false,
  setPttHeld: vi.fn(),
  setInputMode: vi.fn(),
  toggleMute: vi.fn(),
  micActive: true,
}));

vi.mock("@/lib/voice/call-session-context", () => ({
  useCallSession: () => ({
    inputMode: h.inputMode,
    pttHeld: h.pttHeld,
    setPttHeld: h.setPttHeld,
    setInputMode: h.setInputMode,
    toggleMute: h.toggleMute,
    state: { ...INITIAL_CALL_STATE, micActive: h.micActive },
  }),
}));

function renderEl(el: React.JSX.Element) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      {el}
    </NextIntlClientProvider>,
  );
}

beforeEach(() => {
  h.inputMode = "always";
  h.pttHeld = false;
  h.micActive = true;
  h.setPttHeld.mockReset();
  h.setInputMode.mockReset();
  h.toggleMute.mockReset();
});

describe("MicControl", () => {
  it("always mode → a mute toggle bound to the session", () => {
    renderEl(<MicControl />);
    fireEvent.click(screen.getByRole("button", { name: "Mute" }));
    expect(h.toggleMute).toHaveBeenCalledTimes(1);
  });

  it("ptt mode → a hold-to-talk button that drives pttHeld on press/release", () => {
    h.inputMode = "ptt";
    renderEl(<MicControl />);
    const btn = screen.getByRole("button", { name: "Hold to talk" });
    fireEvent.pointerDown(btn);
    expect(h.setPttHeld).toHaveBeenCalledWith(true);
    fireEvent.pointerUp(btn);
    expect(h.setPttHeld).toHaveBeenCalledWith(false);
  });

  it("ptt hold-to-talk is keyboard-operable (Space down/up holds — criterion #7)", () => {
    h.inputMode = "ptt";
    renderEl(<MicControl />);
    const btn = screen.getByRole("button", { name: "Hold to talk" });
    fireEvent.keyDown(btn, { key: " " });
    expect(h.setPttHeld).toHaveBeenCalledWith(true);
    fireEvent.keyUp(btn, { key: " " });
    expect(h.setPttHeld).toHaveBeenCalledWith(false);
  });
});

describe("InputModeToggle", () => {
  it("toggles always → ptt", () => {
    renderEl(<InputModeToggle />);
    fireEvent.click(
      screen.getByRole("button", { name: "Switch to push-to-talk" }),
    );
    expect(h.setInputMode).toHaveBeenCalledWith("ptt");
  });

  it("toggles ptt → always", () => {
    h.inputMode = "ptt";
    renderEl(<InputModeToggle />);
    fireEvent.click(
      screen.getByRole("button", { name: "Switch to always-listening" }),
    );
    expect(h.setInputMode).toHaveBeenCalledWith("always");
  });
});
