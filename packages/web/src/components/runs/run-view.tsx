"use client";

import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { buttonVariants } from "@/components/ui/button";
import type { RunStatusResponse } from "@/lib/api";
import { useRun } from "@/lib/hooks/use-run";
import { cn } from "@/lib/utils";
import { RunStatusBadge } from "./run-status-badge";
import { RunTimeline } from "./run-timeline";

// The live run viewer (T07). Server renders the persona/task brief; this client
// component owns the streaming timeline, status, cancel, and ask-user answers.
export function RunView({
  runId,
  initial,
}: {
  runId: string;
  initial: RunStatusResponse;
}) {
  const t = useTranslations("runs");
  const { view, respond, cancel } = useRun(runId, initial);
  const [cancelling, setCancelling] = useState(false);

  async function onCancel() {
    if (cancelling) return;
    setCancelling(true);
    try {
      await cancel();
    } catch {
      // Cancel is best-effort; the timeline reconciles from the next reload.
    } finally {
      setCancelling(false);
    }
  }

  const runLevelError =
    view.error !== undefined && view.steps.every((s) => s.error === undefined);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <RunStatusBadge status={view.status} />
          {view.tier ? (
            <span
              title={t("tierLabel", { tier: view.tier })}
              className="font-mono text-[0.65rem] tracking-wide text-muted-foreground uppercase"
            >
              {view.tier}
            </span>
          ) : null}
        </div>
        {view.status === "running" ? (
          <button
            type="button"
            onClick={() => void onCancel()}
            disabled={cancelling}
            className={cn(
              buttonVariants({ variant: "outline", size: "sm" }),
              "gap-1.5",
            )}
          >
            <X className="size-3.5" />
            {t("cancel")}
          </button>
        ) : null}
      </div>

      <RunTimeline view={view} onAnswer={respond} />

      {runLevelError ? (
        <p className="text-sm text-destructive">{view.error}</p>
      ) : null}
    </div>
  );
}
