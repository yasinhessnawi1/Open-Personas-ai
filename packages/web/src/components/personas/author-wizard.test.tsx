/**
 * AuthorWizard — describe-phase layout order.
 *
 * The describe phase leads with the free-text "describe your own" path (the
 * textarea + Generate button) and shows the example gallery BELOW it, framed as
 * "or start from an example". This test pins that DOM order so the reorder
 * cannot silently regress, and re-checks the seed → textarea handoff still works.
 *
 * The wizard's API seam (useAuthor) and the createPersona server action are
 * mocked so the describe phase renders without a Clerk provider or a network
 * call — no Generate is triggered here, so neither mock is invoked.
 */

import { fireEvent, render } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { beforeAll, describe, expect, it, vi } from "vitest";
import messages from "@/i18n/messages/en.json";
import { PERSONA_EXAMPLE_CATEGORIES } from "@/lib/persona-examples";
import { AuthorWizard } from "./author-wizard";

// jsdom has no scrollIntoView; the wizard calls it to reveal the seeded textarea
// after a pick. Stub it so the handoff path runs without an unhandled error.
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

// vitest hoists vi.mock above the imports.
vi.mock("@/lib/hooks/use-author", () => ({
  useAuthor: () => ({
    author: vi.fn(async () => ({ yaml: "", questions: [] })),
    refine: vi.fn(async () => ({ yaml: "", questions: [] })),
  }),
}));
vi.mock("@/lib/persona-actions", () => ({
  createPersona: vi.fn(async () => undefined),
}));

function renderWizard() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <AuthorWizard tools={[]} skills={[]} />
    </NextIntlClientProvider>,
  );
}

/** Query an element by data-slot, asserting it exists (narrows away null). */
function bySlot(container: HTMLElement, slot: string): Element {
  const el = container.querySelector(`[data-slot="${slot}"]`);
  expect(el, `missing [data-slot="${slot}"]`).not.toBeNull();
  return el as Element;
}

/** True when `b` follows `a` in document order. */
function isBefore(a: Element, b: Element): boolean {
  return Boolean(
    a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING,
  );
}

describe("AuthorWizard — describe-phase order", () => {
  it("renders the describe-your-own path ABOVE the example gallery", () => {
    const { container } = renderWizard();

    const textarea = bySlot(container, "author-wizard-description");
    const gallery = bySlot(container, "example-gallery");

    // The describe-your-own textarea precedes the gallery in document order.
    expect(isBefore(textarea, gallery)).toBe(true);
  });

  it("places the textarea and Generate button before the first gallery card", () => {
    const { container } = renderWizard();

    const textarea = bySlot(container, "author-wizard-description");
    const generate = bySlot(container, "author-wizard-generate");
    const firstCard = bySlot(container, "example-card");

    expect(isBefore(textarea, firstCard)).toBe(true);
    expect(isBefore(generate, firstCard)).toBe(true);
  });

  it("seeds the textarea when an example card is picked (handoff intact)", () => {
    const { container, getByLabelText } = renderWizard();

    const target = PERSONA_EXAMPLE_CATEGORIES[0].examples[0];
    const label = messages.author.gallery.useNamed.replace(
      "{name}",
      target.name,
    );
    fireEvent.click(getByLabelText(label));

    const textarea = container.querySelector<HTMLTextAreaElement>(
      '[data-slot="author-wizard-description"]',
    );
    expect(textarea?.value).toBe(target.seed);
  });
});
