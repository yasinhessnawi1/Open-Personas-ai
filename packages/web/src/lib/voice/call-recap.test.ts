/**
 * Spec V7 T8 — post-call recap persistence (pure).
 */

import { afterEach, describe, expect, it } from "vitest";
import { type CallRecap, clearRecap, loadRecap, saveRecap } from "./call-recap";

const RECAP: CallRecap = {
  conversationId: "c-1",
  personaName: "Ada",
  durationMs: 125_000,
  endedAt: 1000,
};

afterEach(() => {
  window.localStorage.clear();
});

describe("call-recap", () => {
  it("round-trips a recap per conversation", () => {
    saveRecap(RECAP);
    expect(loadRecap("c-1")).toEqual(RECAP);
  });

  it("is scoped per conversation (a recap for one isn't read for another)", () => {
    saveRecap(RECAP);
    expect(loadRecap("other")).toBeNull();
  });

  it("returns null when none / malformed", () => {
    expect(loadRecap("c-1")).toBeNull();
    window.localStorage.setItem("persona:call-recap:c-1", "{not json");
    expect(loadRecap("c-1")).toBeNull();
  });

  it("clear removes a conversation's recap", () => {
    saveRecap(RECAP);
    clearRecap("c-1");
    expect(loadRecap("c-1")).toBeNull();
  });
});
