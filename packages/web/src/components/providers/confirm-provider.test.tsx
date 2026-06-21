/**
 * Spec 35 cluster M (D-35-12) — ConfirmProvider / useConfirm.
 *
 * Verifies the async confirm contract: the dialog renders the passed title +
 * description; confirming resolves `true`, cancelling (and backdrop/escape via
 * onOpenChange) resolves `false`. Replaces native window.confirm() (§4.5).
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { ConfirmProvider, useConfirm } from "./confirm-provider";

const messages = {
  confirm: {
    cancel: "Cancel",
    confirm: "Confirm",
    delete: "Delete",
    duplicate: "Duplicate",
    deleteTitle: "Delete {name}?",
    duplicateTitle: "Duplicate {name}?",
  },
};

function Harness() {
  const confirm = useConfirm();
  const [result, setResult] = useState("pending");
  return (
    <div>
      <button
        type="button"
        onClick={async () => {
          const ok = await confirm({
            title: "Delete Astrid?",
            description: "This removes the persona and its memory.",
            confirmLabel: "Delete",
            tone: "danger",
          });
          setResult(ok ? "confirmed" : "cancelled");
        }}
      >
        open
      </button>
      <span data-testid="result">{result}</span>
    </div>
  );
}

function renderHarness() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ConfirmProvider>
        <Harness />
      </ConfirmProvider>
    </NextIntlClientProvider>,
  );
}

describe("ConfirmProvider / useConfirm", () => {
  it("renders the title + description when confirm() is called", async () => {
    renderHarness();
    fireEvent.click(screen.getByText("open"));
    expect(await screen.findByText("Delete Astrid?")).toBeInTheDocument();
    expect(
      screen.getByText("This removes the persona and its memory."),
    ).toBeInTheDocument();
  });

  it("resolves true when the confirm action is clicked", async () => {
    renderHarness();
    fireEvent.click(screen.getByText("open"));
    fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
    await waitFor(() =>
      expect(screen.getByTestId("result")).toHaveTextContent("confirmed"),
    );
  });

  it("resolves false when cancelled", async () => {
    renderHarness();
    fireEvent.click(screen.getByText("open"));
    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    await waitFor(() =>
      expect(screen.getByTestId("result")).toHaveTextContent("cancelled"),
    );
  });

  it("throws when used outside a ConfirmProvider", () => {
    function Bare() {
      useConfirm();
      return null;
    }
    // Suppress React's error-boundary console noise for the expected throw.
    expect(() =>
      render(
        <NextIntlClientProvider locale="en" messages={messages}>
          <Bare />
        </NextIntlClientProvider>,
      ),
    ).toThrow(/ConfirmProvider/);
  });
});
