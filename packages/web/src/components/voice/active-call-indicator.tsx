"use client";

/**
 * Spec V7 D-V7-5 — the active-call indicator.
 *
 * A subtle "live" cue rendered wherever a persona appears (its library card /
 * list row, its chat header) — shown ONLY for the persona currently on a call
 * (matched by `personaId` against the one hoisted session), and clearing on
 * end/switch. It is itself the one-tap "return to call": a link to the call's
 * full view. A pure read of the session — never per-component state — so every
 * placement stays consistent across navigation.
 */

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallSession } from "@/lib/voice/call-session-context";

export function ActiveCallIndicator({
  personaId,
}: {
  personaId: string;
}): React.JSX.Element | null {
  const t = useTranslations("voice");
  const { isActive, target } = useCallSession();

  if (!isActive || target === null || target.personaId !== personaId) {
    return null;
  }

  return (
    <Link
      href={`/chat/${target.conversationId}/voice`}
      aria-label={t("indicator.return", { name: target.personaName })}
      data-slot="active-call-indicator"
      className="inline-flex items-center gap-1.5 rounded-full border border-[var(--v-id)] px-2 py-0.5 type-caption normal-case tracking-normal text-[var(--v-id)]"
    >
      <span
        className="size-1.5 animate-pulse rounded-full bg-[var(--v-id)]"
        aria-hidden="true"
      />
      {t("indicator.live")}
    </Link>
  );
}
