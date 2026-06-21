"use client";

/**
 * Spec V7 D-V7-4 — the "Talk to {persona}" entry control.
 *
 * The one-click entry into a call from anywhere a persona+conversation is in
 * context (the chat header today; reused by other anchors). It drives the
 * hoisted session, NOT a route: a click `requestCall`s the target and —
 * depending on the outcome — navigates to the full call view now, or defers to
 * the end-and-switch confirm:
 * - no call active → start + navigate.
 * - this same conversation already on a call → just navigate to its full view.
 * - a *different* call active → the switch confirm opens; navigation waits for it.
 *
 * Replaces the V6 `<Link href=".../voice">`: the link couldn't start the session
 * (the surface auto-started, which T3 removed), and couldn't enforce one call.
 */

import { Phone } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { buttonVariants } from "@/components/ui/button";
import {
  type CallTarget,
  useCallSession,
} from "@/lib/voice/call-session-context";

export interface CallControlProps {
  persona: {
    id: string;
    name: string;
    avatarUrl?: string | null;
    role?: string;
  };
  conversationId: string;
}

export function CallControl({
  persona,
  conversationId,
}: CallControlProps): React.JSX.Element {
  const t = useTranslations("voice");
  const router = useRouter();
  const { requestCall } = useCallSession();

  const onClick = () => {
    const target: CallTarget = {
      personaId: persona.id,
      conversationId,
      personaName: persona.name,
      personaAvatarUrl: persona.avatarUrl ?? undefined,
      personaRole: persona.role,
    };
    // "switch" opens the confirm dialog, which navigates on confirm — don't
    // navigate here, or we'd land on the new call's route before it's confirmed.
    if (requestCall(target) !== "switch") {
      router.push(`/chat/${conversationId}/voice`);
    }
  };

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={t("talk", { name: persona.name })}
      className={buttonVariants({ variant: "secondary", size: "icon" })}
    >
      <Phone aria-hidden />
    </button>
  );
}
