"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/auth";
import type { RunStatusResponse } from "@/lib/api";
import { createApiClient, unwrap } from "@/lib/api/client";
import {
  isTerminal,
  type RunView,
  runViewFromEvents,
  runViewFromSnapshot,
} from "@/lib/run";
import { consumeSSE } from "@/lib/sse";
import { parseRunEvent, type RunEvent } from "@/lib/sse-types";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const TEMPLATE = process.env.NEXT_PUBLIC_CLERK_JWT_TEMPLATE;
const MAX_REATTACH = 3;

/**
 * Run-viewer state + live SSE (spec §4.4, T07). On mount it renders the
 * persisted snapshot; if the run is still running it attaches the live event
 * stream (`GET /runs/:id/events`) and reduces `RunEvent`s into the timeline.
 *
 * Reconnection (spec §8): the SSE queue is single-consumer, so a dropped stream
 * cannot be resumed — on stream end we re-fetch `GET /runs/:id` (the persisted
 * event-log / steps) and reconcile, re-attaching only while still running.
 * Seeding `events` from the initial snapshot makes the reduction idempotent
 * across StrictMode double-mounts and reconnects (keyed by step index).
 */
export function useRun(runId: string, initial: RunStatusResponse) {
  const { getToken } = useAuth();
  const [view, setView] = useState<RunView>(() => runViewFromSnapshot(initial));

  const token = useCallback(
    () => getToken(TEMPLATE ? { template: TEMPLATE } : undefined),
    [getToken],
  );

  const client = useCallback(async () => {
    const jwt = await token();
    return createApiClient(() => Promise.resolve(jwt));
  }, [token]);

  const refetch = useCallback(async (): Promise<RunStatusResponse> => {
    const c = await client();
    return unwrap(
      await c.GET("/v1/runs/{run_id}", { params: { path: { run_id: runId } } }),
    );
  }, [client, runId]);

  useEffect(() => {
    if (isTerminal(initial.status)) return; // already done at load — no stream.

    let cancelled = false;
    const ctrl = new AbortController();
    // Seed from the running snapshot's event-log so reduction is complete even
    // if SSE re-attaches mid-run (idempotent: keyed by step index).
    const events: RunEvent[] = ((initial.steps ?? []) as unknown[]).filter(
      (s): s is RunEvent =>
        typeof s === "object" && s !== null && "timestamp" in s,
    );

    async function drive() {
      for (let attempt = 0; attempt < MAX_REATTACH && !cancelled; attempt++) {
        try {
          const jwt = await token();
          for await (const raw of consumeSSE(`${API}/v1/runs/${runId}/events`, {
            headers: { Authorization: `Bearer ${jwt}` },
            signal: ctrl.signal,
          })) {
            const ev = parseRunEvent(raw); // null on the terminal `end` frame
            if (!ev) continue;
            events.push(ev);
            if (!cancelled) {
              setView(runViewFromEvents(events, { task: initial.task }));
            }
          }
        } catch (e) {
          if (cancelled || (e as Error)?.name === "AbortError") return;
          // SSE 404 (run no longer active) / network blip → fall through to reconcile.
        }
        if (cancelled) return;
        // Stream ended — reconcile from the persisted snapshot (never resume SSE).
        try {
          const snap = await refetch();
          if (cancelled) return;
          setView(runViewFromSnapshot(snap));
          if (isTerminal(snap.status)) return;
        } catch {
          return;
        }
      }
    }

    void drive();
    return () => {
      cancelled = true;
      ctrl.abort();
    };
  }, [runId, initial.status, initial.task, initial.steps, token, refetch]);

  const respond = useCallback(
    async (answer: string) => {
      const c = await client();
      await unwrap(
        await c.POST("/v1/runs/{run_id}/respond", {
          params: { path: { run_id: runId } },
          body: { answer },
        }),
      );
      // Optimistic: mark the awaiting step answered; the SSE `user_responded`
      // (and the eventual reconcile) confirm it.
      setView((v) => ({
        ...v,
        steps: v.steps.map((s) =>
          s.question && !s.answered ? { ...s, answered: true } : s,
        ),
      }));
    },
    [client, runId],
  );

  const cancel = useCallback(async () => {
    const c = await client();
    await unwrap(
      await c.POST("/v1/runs/{run_id}/cancel", {
        params: { path: { run_id: runId } },
      }),
    );
  }, [client, runId]);

  return { view, respond, cancel };
}
