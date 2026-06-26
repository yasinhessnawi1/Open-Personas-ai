"use client";

/**
 * `useInFlightGuard` — single-flight guard for async auth actions (cloud / Clerk).
 *
 * The branded Clerk flows drive each step (verify code, submit password, …) from
 * MORE THAN ONE trigger: the per-digit OTP input auto-fires `onComplete` the
 * moment the 6th digit lands, AND the same action is reachable from the form's
 * `onSubmit` (Enter / the submit button). A fast double-click or double-Enter can
 * also fire one onSubmit handler twice. In every case both calls go out before
 * the hook's `fetchStatus`/`busy` flag flips to "fetching" — so a button
 * `disabled={busy}` does NOT gate the second call. The first call completes the
 * step; the second hits Clerk's "already verified" / "already complete" and 400s,
 * surfacing a spurious error to the user.
 *
 * A synchronous `useRef` latch closes that window: it flips the instant the first
 * call enters (before any await), so the second call returns early. The latch is
 * reset in `finally`, so a genuine retry (after an error) is always allowed.
 *
 * This is a ref (not state) on purpose: state updates are async and batched, so a
 * `useState` flag would update too late to gate a call fired in the same tick.
 */
import { useCallback, useRef } from "react";

/**
 * Wrap an async action so only one invocation can be in flight at a time.
 *
 * @returns `runGuarded(action)` — runs `action` unless one is already in flight
 *   (in which case it returns immediately without invoking it); the latch is
 *   released once `action` settles, so subsequent calls (e.g. a retry) proceed.
 */
export function useInFlightGuard(): {
  runGuarded: (action: () => Promise<void>) => Promise<void>;
} {
  const inFlightRef = useRef(false);

  const runGuarded = useCallback(
    async (action: () => Promise<void>): Promise<void> => {
      // Synchronous check-and-set: the second trigger in the same tick sees the
      // latch already raised and returns before issuing a duplicate request.
      if (inFlightRef.current) return;
      inFlightRef.current = true;
      try {
        await action();
      } finally {
        inFlightRef.current = false;
      }
    },
    [],
  );

  return { runGuarded };
}
