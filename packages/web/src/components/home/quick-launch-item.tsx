import { MessageSquare, Mic } from "lucide-react";
import { getTranslations } from "next-intl/server";
import { startChat, startVoice } from "@/app/actions";
import {
  type AvatarPersona,
  PersonaAvatar,
} from "@/components/persona/persona-avatar";
import { buttonVariants } from "@/components/ui/button";
import { personaIdentityStyle } from "@/lib/persona-identity";
import { cn } from "@/lib/utils";

/**
 * Root-dashboard fast launcher: a COMPACT identity card (real avatar + the
 * identity-underlined name + role + one-click Chat / Call), NOT the full
 * management `<PersonaCard>` grid card. Spec 35 (D-35-1): restyled onto the
 * editorial `.v-card` chrome + identity spine (the derived persona colour drives
 * the name underline + the card's identity accent), so three launchers read as
 * three people. Keeps the real avatar (D-35-9) and the Chat/Call server actions
 * unchanged. The mockup's per-persona conversation/run count chips are omitted —
 * the persona summary carries no such counts and the spec forbids faking.
 *
 * Chat + Call mint a fresh conversation via the co-located server actions (voice
 * has no standalone route; it hangs off a conversation). Server component.
 */
export interface QuickLaunchPersona extends AvatarPersona {
  readonly role: string;
}

export async function QuickLaunchItem({
  persona,
}: {
  persona: QuickLaunchPersona;
}) {
  const t = await getTranslations("home");

  return (
    <div
      className="v-card v-card--pad"
      style={personaIdentityStyle(persona)}
      data-slot="quick-launch-item"
    >
      <div className="flex items-center gap-3.5">
        <PersonaAvatar persona={persona} size="lg" />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="type-body font-heading font-semibold leading-tight">
            <span className="v-id-underline">{persona.name}</span>
          </span>
          <span className="truncate type-ui text-muted-foreground">
            {persona.role}
          </span>
        </div>
      </div>
      <div className="mt-3.5 flex items-center gap-2">
        <form action={startChat.bind(null, persona.id)}>
          <button
            type="submit"
            className={cn(buttonVariants({ size: "sm" }), "gap-1.5")}
          >
            <MessageSquare className="size-4" aria-hidden="true" />
            {t("entry.chat")}
          </button>
        </form>
        <form action={startVoice.bind(null, persona.id)}>
          <button
            type="submit"
            className={cn(
              buttonVariants({ variant: "outline", size: "sm" }),
              "gap-1.5",
            )}
          >
            <Mic className="size-4" aria-hidden="true" />
            {t("entry.call")}
          </button>
        </form>
      </div>
    </div>
  );
}
