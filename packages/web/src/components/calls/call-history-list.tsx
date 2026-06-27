"use client";

/**
 * Spec V9 — the call-history list (the `/calls` page body).
 *
 * A flat reverse-chronological list of the caller's voice calls (the API
 * already returns `started_at DESC`). Each row: `<PersonaAvatar size="sm">` +
 * persona name + a meta line (call time · duration), composed in the same
 * hairline-`border-b` row shape as the conversation list. The whole row links to
 * the saved transcript at `/chat/{conversation_id}` — the spoken turns persist
 * as conversation messages (V9-D-1/D-2), so the existing chat page renders them
 * (no separate transcript renderer). Calls are not deleted independently — a
 * call-record cascades with its conversation — so there is no per-row delete.
 */

import { ChevronRight, Phone } from "lucide-react";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { PersonaAvatar } from "@/components/persona/persona-avatar";
import { formatCallDuration } from "@/lib/calls";

export interface CallHistoryPersona {
  id: string;
  name: string;
  avatar_url: string | null;
}

export interface CallHistoryItem {
  call_id: string;
  conversation_id: string;
  persona_id: string;
  started_at: string;
  duration_s: number | null;
}

export interface CallHistoryListProps {
  calls: readonly CallHistoryItem[];
  personaById: Record<string, CallHistoryPersona>;
}

export function CallHistoryList({ calls, personaById }: CallHistoryListProps) {
  const t = useTranslations("calls");
  const format = useFormatter();

  return (
    <ul className="flex flex-col" data-slot="call-history-list">
      {calls.map((c) => {
        const persona = personaById[c.persona_id];
        const duration = formatCallDuration(c.duration_s);
        return (
          <li
            key={c.call_id}
            className="group/call flex items-center gap-3 border-b py-3"
            data-slot="call-row"
          >
            <Link
              href={`/chat/${c.conversation_id}`}
              className="flex min-w-0 flex-1 items-center gap-3"
            >
              {persona ? (
                <PersonaAvatar persona={persona} size="sm" />
              ) : (
                <span className="size-6 rounded-full bg-muted" aria-hidden />
              )}
              <span className="min-w-0 flex-1 flex-col">
                <span className="type-body block truncate font-medium">
                  {persona ? persona.name : t("unknownPersona")}
                </span>
                <span className="type-caption flex items-center gap-1 text-muted-foreground">
                  <Phone className="size-3 shrink-0" aria-hidden />
                  {format.dateTime(new Date(c.started_at), {
                    dateStyle: "medium",
                    timeStyle: "short",
                  })}
                  {duration ? <span>{` · ${duration}`}</span> : null}
                </span>
              </span>
              <ChevronRight
                className="size-4 shrink-0 text-muted-foreground transition-transform group-hover/call:translate-x-0.5"
                aria-hidden="true"
              />
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
