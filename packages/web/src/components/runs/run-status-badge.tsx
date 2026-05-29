import { useTranslations } from "next-intl";
import type { RunStatus } from "@/lib/run";
import { cn } from "@/lib/utils";

// Status reads as a temperature: live=vermilion pulse, done=cool, faults=warm.
const STATUS_CLASS: Record<RunStatus, string> = {
  running: "border-primary/40 text-primary",
  completed: "border-tier-small/50 text-tier-small",
  cancelled: "border-border text-muted-foreground",
  max_steps_reached: "border-tier-mid/50 text-tier-mid",
  error: "border-destructive/50 text-destructive",
};

export function RunStatusBadge({ status }: { status: RunStatus }) {
  const t = useTranslations("runs");
  return (
    <span
      title={t("statusLabel")}
      data-status={status}
      className={cn(
        "inline-flex w-fit items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[0.65rem] tracking-wide uppercase",
        STATUS_CLASS[status],
      )}
    >
      {status === "running" ? (
        <span className="size-1.5 animate-pulse rounded-full bg-primary" />
      ) : null}
      {t(`status.${status}`)}
    </span>
  );
}
