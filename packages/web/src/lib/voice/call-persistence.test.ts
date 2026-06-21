/**
 * Spec V7 T5 — resume-after-reload persistence (pure logic).
 */

import { afterEach, describe, expect, it } from "vitest";
import {
  clearPersistedCall,
  isResumable,
  loadPersistedCall,
  type PersistedCall,
  persistCall,
  RESUME_FRESHNESS_MS,
} from "./call-persistence";

const RECORD: PersistedCall = {
  conversationId: "c-1",
  personaId: "p-1",
  personaName: "Ada",
  startedAt: 1000,
  lastActiveAt: 1000,
};

afterEach(() => {
  window.sessionStorage.clear();
});

describe("call-persistence", () => {
  it("round-trips a persisted call", () => {
    persistCall(RECORD);
    expect(loadPersistedCall()).toEqual(RECORD);
  });

  it("never persists token or room fields", () => {
    persistCall(RECORD);
    const raw = window.sessionStorage.getItem("persona:active-call") ?? "";
    expect(raw).not.toMatch(/token|room/i);
  });

  it("returns null when nothing is stored", () => {
    expect(loadPersistedCall()).toBeNull();
  });

  it("returns null for a malformed / partial entry", () => {
    window.sessionStorage.setItem("persona:active-call", "{not json");
    expect(loadPersistedCall()).toBeNull();
    window.sessionStorage.setItem(
      "persona:active-call",
      JSON.stringify({ conversationId: "c-1" }),
    );
    expect(loadPersistedCall()).toBeNull();
  });

  it("clear removes the entry", () => {
    persistCall(RECORD);
    clearPersistedCall();
    expect(loadPersistedCall()).toBeNull();
  });

  it("isResumable: fresh within the window, stale beyond it (no auto-dial)", () => {
    const now = 100_000;
    const fresh = { ...RECORD, lastActiveAt: now - 10_000 };
    const stale = { ...RECORD, lastActiveAt: now - (RESUME_FRESHNESS_MS + 1) };
    expect(isResumable(fresh, now)).toBe(true);
    expect(isResumable(stale, now)).toBe(false);
  });

  it("isResumable: a future lastActiveAt (clock skew) never qualifies", () => {
    const now = 100_000;
    expect(isResumable({ ...RECORD, lastActiveAt: now + 5_000 }, now)).toBe(
      false,
    );
  });
});
