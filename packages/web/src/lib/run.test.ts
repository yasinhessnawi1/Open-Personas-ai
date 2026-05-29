import { describe, expect, it } from "vitest";
import type { RunStatusResponse } from "@/lib/api";
import { isTerminal, runViewFromEvents, runViewFromSnapshot } from "./run";
import type { RunEvent } from "./sse-types";

const TS = "2026-05-29T12:00:00Z";

// Typed RunEvent builders (mirror the API's RunEvent constructors).
const ev = {
  started: (task: string): RunEvent => ({
    type: "started",
    step: -1,
    data: { task },
    timestamp: TS,
  }),
  tier: (tier: string): RunEvent => ({
    type: "tier",
    step: -1,
    data: { tier },
    timestamp: TS,
  }),
  thinking: (step: number): RunEvent => ({
    type: "thinking",
    step,
    data: {},
    timestamp: TS,
  }),
  toolCalling: (step: number, name: string, callId: string): RunEvent => ({
    type: "tool_calling",
    step,
    data: {
      tool_names: name,
      tool_calls: [{ name, call_id: callId, args: { q: "x" } }],
    },
    timestamp: TS,
  }),
  toolResult: (step: number, name: string, content: string): RunEvent => ({
    type: "tool_result",
    step,
    data: { tool_name: name, is_error: false, content },
    timestamp: TS,
  }),
  asking: (step: number, question: string): RunEvent => ({
    type: "asking_user",
    step,
    data: { question },
    timestamp: TS,
  }),
  responded: (step: number): RunEvent => ({
    type: "user_responded",
    step,
    data: {},
    timestamp: TS,
  }),
  completed: (step: number, output: string): RunEvent => ({
    type: "completed",
    step,
    data: { output },
    timestamp: TS,
  }),
  finished: (status: string): RunEvent => ({
    type: "finished",
    step: 9,
    data: { run_id: "run_1", status },
    timestamp: TS,
  }),
};

describe("runViewFromEvents", () => {
  it("reduces a multi-step run into an ordered timeline", () => {
    const view = runViewFromEvents(
      [
        ev.started("Plan a trip"),
        ev.tier("mid"),
        ev.thinking(0),
        ev.toolCalling(0, "web_search", "c1"),
        ev.toolResult(0, "web_search", "found 3 results"),
        ev.completed(1, "Here is your plan."),
        ev.finished("completed"),
      ],
      { task: "fallback" },
    );

    expect(view.task).toBe("Plan a trip");
    expect(view.tier).toBe("mid");
    expect(view.status).toBe("completed");
    expect(view.steps).toHaveLength(2);

    const [s0, s1] = view.steps;
    expect(s0.step).toBe(0);
    expect(s0.tools).toHaveLength(1);
    expect(s0.tools[0]).toMatchObject({
      toolName: "web_search",
      result: "found 3 results",
      pending: false,
    });
    expect(s1.final).toBe("Here is your plan.");
    expect(view.output).toBe("Here is your plan.");
  });

  it("is idempotent when events are replayed (reconnect / StrictMode)", () => {
    const events = [
      ev.toolCalling(0, "web_search", "c1"),
      ev.toolResult(0, "web_search", "ok"),
    ];
    // Replaying the same events (as on an SSE reconnect) must not duplicate tools.
    const view = runViewFromEvents([...events, ...events], { task: "t" });
    expect(view.steps).toHaveLength(1);
    expect(view.steps[0].tools).toHaveLength(1);
    expect(view.steps[0].tools[0].pending).toBe(false);
  });

  it("tracks an ask-user question and its answer", () => {
    const open = runViewFromEvents([ev.asking(0, "Which city?")], {
      task: "t",
    });
    expect(open.steps[0].question).toBe("Which city?");
    expect(open.steps[0].answered).toBe(false);

    const answered = runViewFromEvents(
      [ev.asking(0, "Which city?"), ev.responded(0)],
      { task: "t" },
    );
    expect(answered.steps[0].answered).toBe(true);
  });
});

describe("runViewFromSnapshot", () => {
  it("reduces a running snapshot (RunEvent event-log shape)", () => {
    const snap: RunStatusResponse = {
      id: "run_1",
      persona_id: "p1",
      task: "Do a thing",
      status: "running",
      steps: [
        ev.thinking(0) as unknown as Record<string, unknown>,
        ev.toolCalling(0, "web_search", "c1") as unknown as Record<
          string,
          unknown
        >,
      ],
    };
    const view = runViewFromSnapshot(snap);
    expect(view.status).toBe("running");
    expect(view.steps).toHaveLength(1);
    expect(view.steps[0].tools[0].pending).toBe(true);
  });

  it("reduces a terminal snapshot (persisted Step shape), pairing results by call_id", () => {
    const snap: RunStatusResponse = {
      id: "run_1",
      persona_id: "p1",
      task: "Research",
      status: "completed",
      output: "Final answer",
      steps: [
        {
          type: "tool_call",
          tool_calls: [{ name: "web_search", call_id: "c1", args: { q: "x" } }],
          results: [
            {
              tool_name: "web_search",
              call_id: "c1",
              content: "hit",
              is_error: false,
            },
          ],
          tier_used: "small",
        },
        { type: "final", content: "Final answer", tier_used: "mid" },
      ],
    };
    const view = runViewFromSnapshot(snap);
    expect(view.status).toBe("completed");
    expect(view.steps).toHaveLength(2);
    expect(view.steps[0].tools[0]).toMatchObject({
      toolName: "web_search",
      result: "hit",
      isError: false,
      pending: false,
    });
    expect(view.steps[0].tier).toBe("small");
    expect(view.steps[1].final).toBe("Final answer");
  });

  it("prefers the snapshot's top-level status over an event-derived one", () => {
    // A running snapshot whose event-log already contains a completed event:
    // the authoritative top-level status still wins (defensive).
    const snap: RunStatusResponse = {
      id: "run_1",
      persona_id: "p1",
      task: "t",
      status: "cancelled",
      steps: [ev.completed(0, "x") as unknown as Record<string, unknown>],
    };
    expect(runViewFromSnapshot(snap).status).toBe("cancelled");
  });

  it("handles an empty run with no steps", () => {
    const snap: RunStatusResponse = {
      id: "run_1",
      persona_id: "p1",
      task: "t",
      status: "running",
      steps: [],
    };
    const view = runViewFromSnapshot(snap);
    expect(view.steps).toEqual([]);
  });
});

describe("isTerminal", () => {
  it("classifies run statuses", () => {
    expect(isTerminal("running")).toBe(false);
    expect(isTerminal("completed")).toBe(true);
    expect(isTerminal("cancelled")).toBe(true);
    expect(isTerminal("max_steps_reached")).toBe(true);
    expect(isTerminal("error")).toBe(true);
  });
});
