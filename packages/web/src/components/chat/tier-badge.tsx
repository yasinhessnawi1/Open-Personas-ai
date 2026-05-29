"use client";

import { useTranslations } from "next-intl";
import { TIER_BADGE_SETTING, useBoolSetting } from "@/lib/hooks/use-setting";
import { cn } from "@/lib/utils";

// Tier tokens escalate cool→hot (small=slate · mid=amber · frontier=vermilion),
// making the routing layer tangible (spec §4.1).
const TIER_CLASS: Record<string, string> = {
  frontier: "border-tier-frontier/40 text-tier-frontier",
  mid: "border-tier-mid/50 text-tier-mid",
  small: "border-tier-small/50 text-tier-small",
};

export function TierBadge({ tier }: { tier: string }) {
  const t = useTranslations("chat");
  // Power-user setting: hide tier badges (settings toggle, persisted locally).
  const [visible] = useBoolSetting(TIER_BADGE_SETTING, true);
  if (!visible) return null;
  return (
    <span
      title={t("tierLabel", { tier })}
      className={cn(
        "inline-flex w-fit items-center rounded border px-1.5 py-0.5 font-mono text-[0.65rem] tracking-wide uppercase",
        TIER_CLASS[tier] ?? "border-border text-muted-foreground",
      )}
    >
      {tier}
    </span>
  );
}
