"use client";

import { useTranslations } from "next-intl";
import { ToolCallCard } from "@/components/chat/tool-call-card";
import { Card } from "@/components/ui/card";
import { Markdown } from "@/components/ui/markdown";
import type { RunStep } from "@/lib/run";
import { cn } from "@/lib/utils";
import { AskUserPrompt } from "./ask-user-prompt";

export function StepCard({
  step,
  awaiting,
  onAnswer,
}: {
  step: RunStep;
  awaiting: boolean;
  onAnswer: (answer: string) => Promise<void>;
}) {
  const t = useTranslations("runs");
  const isFinal = step.final !== undefined;
  const isError = step.error !== undefined;

  return (
    <li className="relative pl-8">
      {/* Timeline node. Vermilion while this step still awaits input. */}
      <span
        className={cn(
          "absolute top-3 left-[9px] size-2.5 rounded-full ring-4 ring-background",
          isError
            ? "bg-destructive"
            : isFinal
              ? "bg-tier-small"
              : awaiting
                ? "animate-pulse bg-primary"
                : "bg-muted-foreground/40",
        )}
      />
      <Card
        className={cn(
          "gap-2.5 p-4",
          isFinal && "border-tier-small/30",
          isError && "border-destructive/30",
        )}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="font-mono text-[0.65rem] tracking-wide text-muted-foreground uppercase">
            {isFinal ? t("finalLabel") : t("stepLabel", { n: step.step + 1 })}
          </span>
          {step.tier ? (
            <span className="font-mono text-[0.65rem] tracking-wide text-muted-foreground uppercase">
              {step.tier}
            </span>
          ) : null}
        </div>

        {step.tools.length > 0 ? (
          <div className="flex flex-col gap-1.5">
            {step.tools.map((tool, i) => (
              <ToolCallCard key={`${tool.toolName}-${i}`} entry={tool} />
            ))}
          </div>
        ) : null}

        {step.reasoning ? (
          <p className="text-sm leading-relaxed whitespace-pre-wrap text-muted-foreground">
            {step.reasoning}
          </p>
        ) : null}

        {step.question ? (
          <div className="flex flex-col gap-2">
            {awaiting ? (
              <AskUserPrompt question={step.question} onAnswer={onAnswer} />
            ) : (
              <div className="rounded-md border bg-muted/40 p-3">
                <p className="text-sm font-medium">{step.question}</p>
                {step.answered ? (
                  <p className="mt-1 text-xs text-muted-foreground">
                    {t("answered")}
                  </p>
                ) : null}
              </div>
            )}
          </div>
        ) : null}

        {step.final !== undefined ? <Markdown>{step.final}</Markdown> : null}

        {step.maxSteps !== undefined ? (
          <div className="text-sm">
            <p className="mb-1 text-xs text-tier-mid">{t("maxStepsNote")}</p>
            <Markdown>{step.maxSteps}</Markdown>
          </div>
        ) : null}

        {step.error !== undefined ? (
          <p className="text-sm text-destructive">{step.error}</p>
        ) : null}
      </Card>
    </li>
  );
}
