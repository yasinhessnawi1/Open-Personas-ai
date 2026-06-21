/**
 * Spec V7 D-V7-3 — resume-after-reload persistence (pure, sessionStorage-backed).
 *
 * A reload tears down the JS context, so a live WebRTC connection cannot survive
 * (out of scope). What CAN survive is the *intent*: which conversation/persona
 * the user was on a call with. We persist a MINIMAL, non-secret record to
 * `sessionStorage` (tab-scoped, cleared on tab close) so that on the next load we
 * can OFFER to resume — start a fresh call on the same `conversation_id`. We never
 * persist the token or room name: both are dead after a reload (the token is a
 * secret with a short TTL; the room is single-use per session — see the V7
 * research), so storing them would be useless and a needless secret-at-rest.
 *
 * Freshness is anchored on `lastActiveAt` (heartbeated while the call is live),
 * NOT `startedAt`: a 10-minute call that reloads must still be resumable, while a
 * tab abandoned long ago must not auto-offer. Stale entries are discarded — the
 * resume is always a PROMPT, never a silent auto-dial.
 */

const KEY = "persona:active-call";

/** How recently the call must have been active to offer a resume (D-V7-3). */
export const RESUME_FRESHNESS_MS = 90_000;

/** The minimal, non-secret record that survives a reload. */
export interface PersistedCall {
  readonly conversationId: string;
  readonly personaId: string;
  readonly personaName: string;
  readonly personaAvatarUrl?: string;
  readonly personaRole?: string;
  /** Epoch ms the call began (display only). */
  readonly startedAt: number;
  /** Epoch ms the call was last known active — the freshness anchor. */
  readonly lastActiveAt: number;
}

/** sessionStorage, or `null` when unavailable (SSR, or a sandboxed context that
 * throws on access). Callers no-op / return null rather than crash. */
function storage(): Storage | null {
  try {
    return typeof window !== "undefined" ? window.sessionStorage : null;
  } catch {
    return null;
  }
}

/** Write the active-call record (overwrites any prior). */
export function persistCall(record: PersistedCall): void {
  try {
    storage()?.setItem(KEY, JSON.stringify(record));
  } catch {
    // Quota / private-mode write failures are non-fatal — resume is best-effort.
  }
}

/** Remove the active-call record. */
export function clearPersistedCall(): void {
  storage()?.removeItem(KEY);
}

/** Read + validate the active-call record, or `null` if absent/malformed. */
export function loadPersistedCall(): PersistedCall | null {
  const raw = storage()?.getItem(KEY);
  if (!raw) return null;
  try {
    const v = JSON.parse(raw) as Partial<PersistedCall>;
    if (
      typeof v.conversationId === "string" &&
      typeof v.personaId === "string" &&
      typeof v.personaName === "string" &&
      typeof v.startedAt === "number" &&
      typeof v.lastActiveAt === "number"
    ) {
      return {
        conversationId: v.conversationId,
        personaId: v.personaId,
        personaName: v.personaName,
        personaAvatarUrl:
          typeof v.personaAvatarUrl === "string"
            ? v.personaAvatarUrl
            : undefined,
        personaRole:
          typeof v.personaRole === "string" ? v.personaRole : undefined,
        startedAt: v.startedAt,
        lastActiveAt: v.lastActiveAt,
      };
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Whether `record` is fresh enough to offer a resume: last active within the
 * window, and not in the future (a clock skew / corrupt entry never qualifies).
 */
export function isResumable(
  record: PersistedCall,
  now: number,
  windowMs: number = RESUME_FRESHNESS_MS,
): boolean {
  const age = now - record.lastActiveAt;
  return age >= 0 && age <= windowMs;
}
