/**
 * Spec V7 D-V7-7 — post-call recap persistence (pure, web-derived).
 *
 * A finished call should leave a navigable trace in the shared thread. We record
 * it from the call LIFECYCLE the session already owns — `{persona, duration}` per
 * conversation — into `localStorage`, so the chat thread can render a "call ended
 * · N min" entry after the fact (the session itself clears on end). This is a
 * web-DERIVED affordance, deliberately independent of whether voice turns are
 * persisted as messages (that's V9's concern). The DURABLE `origin=call` marker
 * stays V9's (forward Seam B) — this writes no server state.
 */

const PREFIX = "persona:call-recap:";

export interface CallRecap {
  readonly conversationId: string;
  readonly personaName: string;
  /** Call duration in ms (start → end). */
  readonly durationMs: number;
  /** Epoch ms the call ended. */
  readonly endedAt: number;
}

function storage(): Storage | null {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null;
  }
}

/** Record the recap for a conversation (overwrites any prior recap for it). */
export function saveRecap(recap: CallRecap): void {
  try {
    storage()?.setItem(PREFIX + recap.conversationId, JSON.stringify(recap));
  } catch {
    // best-effort — a recap is chrome, never load-bearing.
  }
}

/** Read the recap for a conversation, or `null` if none / malformed. */
export function loadRecap(conversationId: string): CallRecap | null {
  const raw = storage()?.getItem(PREFIX + conversationId);
  if (!raw) return null;
  try {
    const v = JSON.parse(raw) as Partial<CallRecap>;
    if (
      typeof v.conversationId === "string" &&
      typeof v.personaName === "string" &&
      typeof v.durationMs === "number" &&
      typeof v.endedAt === "number"
    ) {
      return {
        conversationId: v.conversationId,
        personaName: v.personaName,
        durationMs: v.durationMs,
        endedAt: v.endedAt,
      };
    }
    return null;
  } catch {
    return null;
  }
}

/** Remove a conversation's recap (on dismiss, or when a new call starts on it). */
export function clearRecap(conversationId: string): void {
  storage()?.removeItem(PREFIX + conversationId);
}
