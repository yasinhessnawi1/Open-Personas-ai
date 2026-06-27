/**
 * Structural tests for the app-sidebar section bodies.
 *
 * Asserts the chat-app MESSAGES contract (title = persona name, brief =
 * conversation title, untitled/unknown fallbacks, active row, empty state,
 * collapsed-mode label suppression) and the PERSONAS rail links.
 */
import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";
import type {
  SidebarCall,
  SidebarConversation,
  SidebarPersona,
} from "./sidebar-data";
import { CallsList, MessagesList, PersonasRail } from "./sidebar-sections";

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ getToken: async () => null }),
}));

let pathname = "/";
vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
}));

const messages = {
  nav: {
    sidebar: {
      messagesEmpty: "No conversations yet",
      untitled: "Untitled conversation",
      unknownPersona: "Unknown persona",
      callsEmpty: "No calls yet",
      callOngoing: "Call",
    },
  },
};

const astrid: SidebarPersona = {
  id: "astrid",
  name: "Astrid",
  role: "Tenancy",
  created_at: "2026-01-01",
  avatar_url: null,
};

function wrap(ui: React.ReactNode) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      {ui}
    </NextIntlClientProvider>,
  );
}

describe("MessagesList", () => {
  it("renders persona name as the title line and conversation title as the brief", () => {
    const rows: SidebarConversation[] = [
      {
        id: "c1",
        title: "Rent dispute",
        updated_at: "2026-06-10T00:00:00Z",
        persona: astrid,
      },
    ];
    wrap(<MessagesList conversations={rows} collapsed={false} />);
    expect(screen.getByText("Astrid")).toBeInTheDocument();
    expect(screen.getByText("Rent dispute")).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute("href", "/chat/c1");
  });

  it("falls back to untitled brief and unknown-persona title", () => {
    const rows: SidebarConversation[] = [
      {
        id: "c2",
        title: "   ",
        updated_at: "2026-06-10T00:00:00Z",
        persona: null,
      },
    ];
    wrap(<MessagesList conversations={rows} collapsed={false} />);
    expect(screen.getByText("Unknown persona")).toBeInTheDocument();
    expect(screen.getByText("Untitled conversation")).toBeInTheDocument();
  });

  it("marks the active conversation with aria-current", () => {
    pathname = "/chat/c1";
    const rows: SidebarConversation[] = [
      {
        id: "c1",
        title: "Rent dispute",
        updated_at: "2026-06-10T00:00:00Z",
        persona: astrid,
      },
    ];
    wrap(<MessagesList conversations={rows} collapsed={false} />);
    expect(screen.getByRole("link")).toHaveAttribute("aria-current", "page");
    pathname = "/";
  });

  it("renders the empty state when expanded with no conversations", () => {
    wrap(<MessagesList conversations={[]} collapsed={false} />);
    expect(screen.getByText("No conversations yet")).toBeInTheDocument();
  });

  it("renders nothing when collapsed with no conversations", () => {
    const { container } = wrap(<MessagesList conversations={[]} collapsed />);
    expect(container).toBeEmptyDOMElement();
  });

  it("suppresses the visible brief text in collapsed mode", () => {
    const rows: SidebarConversation[] = [
      {
        id: "c1",
        title: "Rent dispute",
        updated_at: "2026-06-10T00:00:00Z",
        persona: astrid,
      },
    ];
    wrap(<MessagesList conversations={rows} collapsed />);
    // The brief is not rendered as text in the rail; the link is avatar-only.
    expect(screen.queryByText("Rent dispute")).not.toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute("href", "/chat/c1");
  });
});

describe("CallsList", () => {
  const callRow = (over: Partial<SidebarCall> = {}): SidebarCall => ({
    callId: "call_1",
    conversationId: "conv_1",
    startedAt: "2026-06-10T00:00:00Z",
    durationS: 125,
    persona: astrid,
    ...over,
  });

  it("renders persona name + m:ss duration and links the row to the transcript", () => {
    wrap(<CallsList calls={[callRow()]} collapsed={false} />);
    expect(screen.getByText("Astrid")).toBeInTheDocument();
    expect(screen.getByText("2:05")).toBeInTheDocument(); // 125s → 2:05
    // the row links to the SAVED TRANSCRIPT (the chat page renders voice turns).
    expect(screen.getByRole("link")).toHaveAttribute("href", "/chat/conv_1");
  });

  it("falls back to a generic label for a live call (null duration)", () => {
    wrap(
      <CallsList calls={[callRow({ durationS: null })]} collapsed={false} />,
    );
    expect(screen.getByText("Call")).toBeInTheDocument();
  });

  it("falls back to unknown-persona when the persona is missing", () => {
    wrap(<CallsList calls={[callRow({ persona: null })]} collapsed={false} />);
    expect(screen.getByText("Unknown persona")).toBeInTheDocument();
  });

  it("marks the active call row with aria-current", () => {
    pathname = "/chat/conv_1";
    wrap(<CallsList calls={[callRow()]} collapsed={false} />);
    expect(screen.getByRole("link")).toHaveAttribute("aria-current", "page");
    pathname = "/";
  });

  it("renders the empty state when expanded with no calls", () => {
    wrap(<CallsList calls={[]} collapsed={false} />);
    expect(screen.getByText("No calls yet")).toBeInTheDocument();
  });

  it("renders nothing when collapsed with no calls", () => {
    const { container } = wrap(<CallsList calls={[]} collapsed />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("PersonasRail", () => {
  it("links each persona to its page", () => {
    wrap(<PersonasRail personas={[astrid]} collapsed={false} />);
    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      "/personas/astrid",
    );
  });

  it("renders nothing when there are no personas", () => {
    const { container } = wrap(
      <PersonasRail personas={[]} collapsed={false} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
