/**
 * Spec F5 T09 — structural tests for <PersonaLibraryCard>.
 *
 * Verifies the action menu surface (View / Edit / Duplicate / Delete) and
 * that the wrapper composes `<PersonaCard>` with the `glass-card` class.
 * Behavioural mutation wiring (duplicate / delete server roundtrips) lands
 * at T11 with richer Sheet-based confirmations.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConfirmProvider } from "@/components/providers/confirm-provider";
import { NotificationProvider } from "@/components/providers/notification-provider";
import { PersonaLibraryCard } from "./persona-library-card";

const h = vi.hoisted(() => ({
  push: vi.fn(),
  requestCall: vi.fn(() => "started" as "started" | "current" | "switch"),
  post: vi.fn(async () => ({ data: { id: "new-conv" } })),
}));

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ getToken: async () => null }),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: h.push }),
}));
vi.mock("@/app/actions", () => ({
  startChat: vi.fn(),
  startVoice: vi.fn(),
}));
vi.mock("@/lib/api/use-api", () => ({
  useApi: () => ({ POST: h.post, GET: vi.fn(), DELETE: vi.fn() }),
}));
vi.mock("@/lib/voice/call-session-context", () => ({
  useCallSession: () => ({ requestCall: h.requestCall }),
}));

const messages = {
  personas: {
    library: {
      menuLabel: "Actions for {name}",
      chat: "Chat",
      call: "Voice call",
      appsTools: "{count, plural, one {# app & tool} other {# apps & tools}}",
      skillsCount: "{count, plural, one {# skill} other {# skills}}",
      constraintsCount:
        "{count, plural, one {# constraint} other {# constraints}}",
      chats: "{count, plural, =0 {No chats} one {# chat} other {# chats}}",
      view: "View",
      edit: "Edit",
      duplicate: "Duplicate as template",
      delete: "Delete",
      duplicateConfirm: "dup",
      deleteConfirm: "del",
    },
  },
  confirm: {
    cancel: "Cancel",
    confirm: "Confirm",
    delete: "Delete",
    duplicate: "Duplicate",
    deleteTitle: "Delete {name}?",
    duplicateTitle: "Duplicate {name}?",
  },
};

const FIXTURE = {
  id: "astrid",
  name: "Astrid",
  role: "Tenancy law",
  language: "no",
  tools_count: 3,
  skills_count: 1,
  constraints_count: 2,
  conversation_count: 5,
};

function renderCard() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <NotificationProvider>
        <ConfirmProvider>
          <PersonaLibraryCard persona={FIXTURE} />
        </ConfirmProvider>
      </NotificationProvider>
    </NextIntlClientProvider>,
  );
}

describe("PersonaLibraryCard — T09 structural surface", () => {
  beforeEach(() => {
    h.push.mockReset();
    h.requestCall.mockReset();
    h.requestCall.mockReturnValue("started");
    h.post.mockClear();
  });

  it("call entry routes through the session (mints a conversation → requestCall → navigate)", async () => {
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "Voice call" }));
    await waitFor(() => expect(h.post).toHaveBeenCalledTimes(1));
    expect(h.requestCall).toHaveBeenCalledWith(
      expect.objectContaining({
        personaId: "astrid",
        conversationId: "new-conv",
        personaName: "Astrid",
      }),
    );
    expect(h.push).toHaveBeenCalledWith("/chat/new-conv/voice");
  });

  it("call entry does NOT navigate when a switch confirm is pending (no bypass)", async () => {
    h.requestCall.mockReturnValue("switch");
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "Voice call" }));
    await waitFor(() => expect(h.requestCall).toHaveBeenCalled());
    expect(h.push).not.toHaveBeenCalled();
  });

  it("renders the menu trigger with persona-named aria-label", () => {
    renderCard();
    const trigger = screen.getByLabelText("Actions for Astrid");
    expect(trigger).toBeInTheDocument();
  });

  it("renders the capability glance + chat count from the summary (Spec 35)", () => {
    renderCard();
    // language chip, apps&tools (folds MCP), and the chat count — all free.
    expect(screen.getByText("no")).toBeInTheDocument();
    expect(screen.getByTitle("3 apps & tools")).toBeInTheDocument();
    expect(screen.getByText("5 chats")).toBeInTheDocument();
  });

  it("renders the identity .v-card surface (Spec 35 restyle)", () => {
    const { container } = renderCard();
    // The library card is now the editorial identity card, not the glass card.
    const card = container.querySelector(
      '[data-slot="persona-library-card"].v-card',
    );
    expect(card).toBeInTheDocument();
  });

  it("renders a card-body Link href pointing to the detail route", () => {
    renderCard();
    const links = screen.getAllByRole("link");
    // At least one link points at /personas/astrid (the card body wrapping).
    expect(
      links.some((a) => a.getAttribute("href") === "/personas/astrid"),
    ).toBe(true);
  });
});
