import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";
import {
  type AvatarPersona,
  PersonaAvatar,
} from "@/components/persona/persona-avatar";
import { personaIdentityStyle } from "@/lib/persona-identity";
import { cn } from "@/lib/utils";

/**
 * Root-dashboard "resume" list: the caller's most-recent conversations, each a
 * one-click jump back into the thread. Reuses the existing `/v1/conversations`
 * data (already sorted `updated_at DESC`) so no new endpoint is needed. Spec 35
 * (D-35-1): restyled onto a single `.v-card` with identity-spine rows — the real
 * persona avatar + the identity-underlined persona name carry the colour. The
 * mockup's per-row tier chip is omitted: the conversation-list summary carries
 * no tier (it would require an N+1 fetch), and the spec forbids faking — the
 * tier chip lives on the chat surface, on real per-message data.
 *
 * Server component — pure presentational; the resolved data is passed in.
 */
export interface RecentConversationItem {
  readonly id: string;
  readonly title: string;
  readonly updated_at: string;
  readonly persona: AvatarPersona | null;
}

export async function RecentConversations({
  conversations,
}: {
  conversations: readonly RecentConversationItem[];
}) {
  const t = await getTranslations("home");
  const format = await getFormatter();

  return (
    <ul
      className="v-card flex flex-col overflow-hidden"
      data-slot="recent-conversations"
    >
      {conversations.map((c, i) => (
        <li key={c.id}>
          <Link
            href={`/chat/${c.id}`}
            style={c.persona ? personaIdentityStyle(c.persona) : undefined}
            className={cn(
              "group/recent flex items-center gap-3.5 px-4 py-3.5 outline-none transition-colors duration-[var(--motion-duration-fast)] hover:bg-muted focus-visible:bg-muted motion-reduce:transition-none",
              i > 0 && "border-t",
            )}
          >
            {c.persona ? (
              <PersonaAvatar persona={c.persona} size="md" />
            ) : (
              <span
                className="size-10 shrink-0 rounded-full bg-muted"
                aria-hidden
              />
            )}
            <span className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="type-body block truncate font-medium">
                {c.title || t("recent.untitled")}
              </span>
              <span className="truncate type-ui text-muted-foreground">
                <span className="v-id-underline">
                  {c.persona ? c.persona.name : t("recent.unknownPersona")}
                </span>
                {" · "}
                {format.dateTime(new Date(c.updated_at), {
                  dateStyle: "medium",
                })}
              </span>
            </span>
            <ChevronRight
              className="size-4 shrink-0 text-muted-foreground transition-transform duration-[var(--motion-duration-fast)] group-hover/recent:translate-x-0.5 motion-reduce:transition-none motion-reduce:group-hover/recent:translate-x-0"
              aria-hidden="true"
            />
          </Link>
        </li>
      ))}
    </ul>
  );
}
