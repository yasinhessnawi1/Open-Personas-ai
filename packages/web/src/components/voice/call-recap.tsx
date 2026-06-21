"use client";

/**
 * Spec V7 D-V7-7 — the post-call recap entry.
 *
 * A subtle "Call ended · N min · view transcript" trace in the chat thread,
 * derived from the call lifecycle the session recorded on end (no server write;
 * the durable `origin=call` marker stays V9's). Voice + text share the
 * conversation, so "view transcript" links to the thread itself. Dismissible.
 */

import { Phone, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import {
  type CallRecap as CallRecapRecord,
  clearRecap,
  loadRecap,
} from "@/lib/voice/call-recap";

export function CallRecap({
  conversationId,
}: {
  conversationId: string;
}): React.JSX.Element | null {
  const t = useTranslations("voice");
  const [recap, setRecap] = useState<CallRecapRecord | null>(null);

  // Read on the client (localStorage) after hydration — and re-read on focus, so
  // ending a call in the mini-bar then returning to this thread shows the trace.
  useEffect(() => {
    const read = () => setRecap(loadRecap(conversationId));
    read();
    window.addEventListener("focus", read);
    return () => window.removeEventListener("focus", read);
  }, [conversationId]);

  if (recap === null) return null;

  const minutes = Math.floor(recap.durationMs / 60_000);
  const duration =
    minutes < 1 ? t("recap.short") : t("recap.minutes", { count: minutes });

  const dismiss = () => {
    clearRecap(conversationId);
    setRecap(null);
  };

  return (
    <div
      data-slot="call-recap"
      className="mx-auto flex w-fit items-center gap-2 rounded-full border bg-muted/40 px-3 py-1 type-caption normal-case tracking-normal text-muted-foreground"
    >
      <Phone className="size-3.5" aria-hidden="true" />
      {/* The trace itself — "Call ended · N min" — IS the navigable mark in the
          thread (deliverable #7). A full transcript VIEW is V9 (call history &
          transcripts), forward Seam B — V7 doesn't link to a transcript it can't
          honestly provide. */}
      <span>{t("recap.summary", { duration })}</span>
      <button
        type="button"
        onClick={dismiss}
        aria-label={t("recap.dismiss")}
        className="text-muted-foreground hover:text-foreground"
      >
        <X className="size-3.5" aria-hidden="true" />
      </button>
    </div>
  );
}
