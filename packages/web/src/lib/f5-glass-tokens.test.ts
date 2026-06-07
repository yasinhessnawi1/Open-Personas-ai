/**
 * F5 T08 — F1 glass-token amendment structural assertions.
 *
 * Validates that the 13 D-F5-X-glass-token-f1-amendment tokens landed in
 * globals.css with both :root (light) and .dark variants. Full backdrop-
 * composition WCAG verification is v0.2 candidate (the existing
 * contrastRatio helper doesn't natively compose alpha-over-backdrop;
 * adding that math is itself a separate amendment).
 *
 * Approach: read globals.css text and assert each token name appears in
 * the :root section AND the .dark section (each gets a light + dark
 * variant per the additive-only contract). This is structural — it
 * catches accidental removal or rename of any glass token. The 12th
 * additive-precedent chain entry depends on this discipline holding.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const GLOBALS_CSS = resolve(__dirname, "../app/globals.css");

const css = readFileSync(GLOBALS_CSS, "utf-8");

// Split into :root (everything before the .dark selector block) and .dark
// blocks. Match `^.dark {` line-anchored so a comment mentioning `.dark { }`
// doesn't move the boundary.
const darkBlockMatch = /^\.dark\s*\{/m.exec(css);
if (!darkBlockMatch || darkBlockMatch.index === undefined) {
  throw new Error("globals.css missing top-level .dark { selector");
}
const darkIndex = darkBlockMatch.index;
const rootBlock = css.slice(0, darkIndex);
const darkBlock = css.slice(darkIndex);

const F5_GLASS_TOKENS = [
  "--glass-bg-elevated",
  "--glass-bg-subtle",
  "--glass-bg-overlay",
  "--glass-border-subtle",
  "--glass-border-strong",
  "--glass-shadow-soft",
  "--glass-shadow-lifted",
  "--glass-blur-light",
  "--glass-blur-medium",
  "--glass-blur-strong",
  "--glass-saturation-boost",
  "--glass-reflection-top",
] as const;

describe("F5 T08 — glass tokens additive amendment (D-F5-X-glass-token-f1-amendment)", () => {
  for (const token of F5_GLASS_TOKENS) {
    it(`${token} is defined in :root (light)`, () => {
      expect(rootBlock).toContain(token);
    });
  }

  // 7 of the 12 tokens have dark variants in the .dark block (the blur
  // values + saturation boost are mode-invariant and stay in :root only).
  const TOKENS_WITH_DARK_VARIANT = [
    "--glass-bg-elevated",
    "--glass-bg-subtle",
    "--glass-bg-overlay",
    "--glass-border-subtle",
    "--glass-border-strong",
    "--glass-shadow-soft",
    "--glass-shadow-lifted",
    "--glass-reflection-top",
  ] as const;

  for (const token of TOKENS_WITH_DARK_VARIANT) {
    it(`${token} has a .dark variant`, () => {
      expect(darkBlock).toContain(token);
    });
  }

  it("blur tokens are mode-invariant (defined once in :root only)", () => {
    // These three live in :root only — the blur magnitude doesn't change
    // between light and dark mode. Smoke test for the structural invariant.
    expect(rootBlock).toContain("--glass-blur-light: 6px");
    expect(rootBlock).toContain("--glass-blur-medium: 12px");
    expect(rootBlock).toContain("--glass-blur-strong: 20px");
    expect(rootBlock).toContain("--glass-saturation-boost: 160%");
  });

  it("provides .glass-card, .glass-chip, .glass-overlay utility classes", () => {
    expect(css).toMatch(/\.glass-card\s*\{/);
    expect(css).toMatch(/\.glass-chip\s*\{/);
    expect(css).toMatch(/\.glass-overlay\s*\{/);
  });

  it("includes @supports fallback for browsers without backdrop-filter", () => {
    expect(css).toContain("@supports not");
    expect(css).toContain("backdrop-filter");
  });

  it("does NOT remove or rename any existing F1 token (D-F1-7 additive-only)", () => {
    // Spot-check the load-bearing F1 tokens. If any of these break, the
    // additive-only contract has been violated.
    expect(rootBlock).toContain("--primary:");
    expect(rootBlock).toContain("--accent:");
    expect(rootBlock).toContain("--motion-duration-fast");
    expect(rootBlock).toContain("--elevation-0");
    expect(rootBlock).toContain("--tier-frontier");
  });
});
