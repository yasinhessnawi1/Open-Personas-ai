/**
 * Spec V7 T7 — voice input preferences (pure persistence).
 */

import { afterEach, describe, expect, it } from "vitest";
import {
  DEFAULT_INPUT_PREFS,
  loadInputPrefs,
  saveInputPrefs,
} from "./input-prefs";

afterEach(() => {
  window.localStorage.clear();
});

describe("input-prefs", () => {
  it("defaults to always-listening when nothing is saved", () => {
    expect(loadInputPrefs()).toEqual(DEFAULT_INPUT_PREFS);
    expect(loadInputPrefs().mode).toBe("always");
  });

  it("round-trips a saved preference (persists across reads)", () => {
    saveInputPrefs({ mode: "ptt", pttKey: "KeyV" });
    expect(loadInputPrefs()).toEqual({ mode: "ptt", pttKey: "KeyV" });
  });

  it("coerces an unknown mode back to always and a missing key to the default", () => {
    window.localStorage.setItem(
      "persona:voice-input-prefs",
      JSON.stringify({ mode: "bogus" }),
    );
    expect(loadInputPrefs()).toEqual(DEFAULT_INPUT_PREFS);
  });

  it("falls back to defaults on malformed JSON", () => {
    window.localStorage.setItem("persona:voice-input-prefs", "{not json");
    expect(loadInputPrefs()).toEqual(DEFAULT_INPUT_PREFS);
  });
});
