/**
 * Unit tests for `useInFlightGuard` — the single-flight latch that prevents the
 * branded Clerk auth steps from double-firing (OTP `onComplete` + form
 * `onSubmit`, or a double-click before `fetchStatus` flips).
 */
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useInFlightGuard } from "./use-in-flight-guard.cloud";

/** A promise plus its resolver, so a test can hold an action "in flight". */
function deferred(): { promise: Promise<void>; resolve: () => void } {
  let resolve!: () => void;
  const promise = new Promise<void>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

describe("useInFlightGuard", () => {
  it("runs the action exactly once when fired twice in the same tick", async () => {
    const { result } = renderHook(() => useInFlightGuard());
    const gate = deferred();
    let calls = 0;
    const action = () => {
      calls += 1;
      return gate.promise;
    };

    // Two synchronous triggers (the OTP onComplete + the form onSubmit) for one
    // code entry: only the first must reach the action.
    let first!: Promise<void>;
    let second!: Promise<void>;
    act(() => {
      first = result.current.runGuarded(action);
      second = result.current.runGuarded(action);
    });
    expect(calls).toBe(1);

    await act(async () => {
      gate.resolve();
      await Promise.all([first, second]);
    });
    expect(calls).toBe(1);
  });

  it("releases the latch so a later call (e.g. a retry) runs", async () => {
    const { result } = renderHook(() => useInFlightGuard());
    let calls = 0;
    const action = () => {
      calls += 1;
      return Promise.resolve();
    };

    await act(async () => {
      await result.current.runGuarded(action);
    });
    await act(async () => {
      await result.current.runGuarded(action);
    });
    expect(calls).toBe(2);
  });

  it("releases the latch even when the action rejects", async () => {
    const { result } = renderHook(() => useInFlightGuard());
    let calls = 0;
    const failing = () => {
      calls += 1;
      return Promise.reject(new Error("boom"));
    };

    await act(async () => {
      await expect(result.current.runGuarded(failing)).rejects.toThrow("boom");
    });
    // A subsequent call must not be blocked by the failed one.
    await act(async () => {
      await expect(result.current.runGuarded(failing)).rejects.toThrow("boom");
    });
    expect(calls).toBe(2);
  });
});
