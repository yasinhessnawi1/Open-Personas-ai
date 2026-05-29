"use client";

import { useTranslations } from "next-intl";
import type { RunView } from "@/lib/run";
import { StepCard } from "./step-card";

export function RunTimeline({
  view,
  onAnswer,
}: {
  view: RunView;
  onAnswer: (answer: string) => Promise<void>;
}) {
  const t = useTranslations("runs");
  const running = view.status === "running";
  const awaitingStep = running
    ? view.steps.find((s) => s.question && !s.answered)?.step
    : undefined;

  if (view.steps.length === 0 && !running) {
    return <p className="text-sm text-muted-foreground">{t("noSteps")}</p>;
  }

  return (
    <div className="relative">
      {view.steps.length > 0 ? (
        <span
          aria-hidden
          className="absolute top-3 bottom-3 left-[14px] w-px bg-border"
        />
      ) : null}
      <ol className="flex flex-col gap-3">
        {view.steps.map((s) => (
          <StepCard
            key={s.step}
            step={s}
            awaiting={s.step === awaitingStep}
            onAnswer={onAnswer}
          />
        ))}
      </ol>
      {running && awaitingStep === undefined ? (
        <div className="mt-3 flex items-center gap-2 pl-8 text-sm text-muted-foreground">
          <span className="size-2 animate-pulse rounded-full bg-primary" />
          {t("working")}
        </div>
      ) : null}
    </div>
  );
}
