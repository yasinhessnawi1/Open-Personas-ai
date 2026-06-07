/**
 * Spec F5 T09 — structural tests for <PersonaLibraryCard>.
 *
 * Verifies the action menu surface (View / Edit / Duplicate / Delete) and
 * that the wrapper composes `<PersonaCard>` with the `glass-card` class.
 * Behavioural mutation wiring (duplicate / delete server roundtrips) lands
 * at T11 with richer Sheet-based confirmations.
 */
import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";
import { PersonaLibraryCard } from "./persona-library-card";

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ getToken: async () => null }),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

const messages = {
  personas: {
    library: {
      menuLabel: "Actions for {name}",
      view: "View",
      edit: "Edit",
      duplicate: "Duplicate as template",
      delete: "Delete",
      duplicateConfirm: "dup",
      deleteConfirm: "del",
    },
  },
};

const FIXTURE = { id: "astrid", name: "Astrid", role: "Tenancy law" };

function renderCard() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <PersonaLibraryCard persona={FIXTURE} />
    </NextIntlClientProvider>,
  );
}

describe("PersonaLibraryCard — T09 structural surface", () => {
  it("renders the menu trigger with persona-named aria-label", () => {
    renderCard();
    const trigger = screen.getByLabelText("Actions for Astrid");
    expect(trigger).toBeInTheDocument();
  });

  it("composes <PersonaCard> with the glass-card class", () => {
    const { container } = renderCard();
    // glass-card lives on the inner card body via the className prop drill.
    const glass = container.querySelector(".glass-card");
    expect(glass).toBeInTheDocument();
  });

  it("renders a PersonaCard Link href pointing to the detail route", () => {
    renderCard();
    const links = screen.getAllByRole("link");
    // At least one link points at /personas/astrid (the card body wrapping).
    expect(
      links.some((a) => a.getAttribute("href") === "/personas/astrid"),
    ).toBe(true);
  });
});
