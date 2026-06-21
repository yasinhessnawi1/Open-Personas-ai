/**
 * Spec V7 T5 — the resume-after-reload prompt.
 *
 * Asserts: hidden when nothing resumable; shows the persona; resume → resumeCall
 * + navigate to the call; dismiss → dismissResume, no navigation. (The freshness
 * / sessionStorage logic is owned by `call-persistence.test.ts`.)
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";
import messages from "@/i18n/messages/en.json";
import type { PersistedCall } from "@/lib/voice/call-persistence";
import type { CallSession } from "@/lib/voice/call-session-context";
import { ResumeCallPrompt } from "./resume-call-prompt";

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

const RESUMABLE: PersistedCall = {
  conversationId: "c-1",
  personaId: "p-1",
  personaName: "Ada",
  startedAt: 1000,
  lastActiveAt: 1000,
};

function renderPrompt() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ResumeCallPrompt />
    </NextIntlClientProvider>,
  );
}

beforeEach(() => {
  h.push.mockReset();
});

describe("ResumeCallPrompt", () => {
  it("renders nothing when there's no resumable call", () => {
    h.session = { resumable: null };
    const { container } = renderPrompt();
    expect(
      container.querySelector('[data-slot="resume-call-prompt"]'),
    ).toBeNull();
  });

  it("offers the persona and resumes on confirm (then navigates to the call)", () => {
    const resumeCall = vi.fn();
    h.session = { resumable: RESUMABLE, resumeCall, dismissResume: vi.fn() };
    renderPrompt();
    expect(screen.getByRole("dialog")).toHaveAccessibleName(/Resume your call/);
    expect(screen.getByText(/Ada/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Resume call" }));
    expect(resumeCall).toHaveBeenCalledTimes(1);
    expect(h.push).toHaveBeenCalledWith("/chat/c-1/voice");
  });

  it("dismiss forgets the call without navigating", () => {
    const dismissResume = vi.fn();
    h.session = { resumable: RESUMABLE, resumeCall: vi.fn(), dismissResume };
    renderPrompt();
    fireEvent.click(screen.getByRole("button", { name: "Not now" }));
    expect(dismissResume).toHaveBeenCalledTimes(1);
    expect(h.push).not.toHaveBeenCalled();
  });
});
