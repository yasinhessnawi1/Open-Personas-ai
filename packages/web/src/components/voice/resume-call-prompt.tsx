"use client";

/**
 * Spec V7 D-V7-3 — the resume-after-reload prompt.
 *
 * Rendered once in the shell. On load, if a recent call was found in
 * `sessionStorage` (the `resumable` candidate), this offers to reconnect — a
 * PROMPT, never a silent auto-dial. Confirming starts a FRESH call on the same
 * `conversation_id` (a reconnect, not a preserved connection — WebRTC can't
 * survive a reload) and navigates to the full call view; dismissing forgets it.
 *
 * A non-blocking bottom-anchored card (not a modal — there's nothing destructive
 * to gate): `role="dialog"`, labelled + described, the resume action auto-focuses.
 */

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { useCallSession } from "@/lib/voice/call-session-context";

export function ResumeCallPrompt(): React.JSX.Element | null {
  const t = useTranslations("voice");
  const router = useRouter();
  const { resumable, resumeCall, dismissResume } = useCallSession();

  if (resumable === null) return null;

  const onResume = () => {
    const conversationId = resumable.conversationId;
    resumeCall();
    router.push(`/chat/${conversationId}/voice`);
  };

  return (
    <div
      role="dialog"
      aria-labelledby="resume-call-title"
      aria-describedby="resume-call-body"
      data-slot="resume-call-prompt"
      className="fixed inset-x-0 bottom-4 z-40 mx-auto w-[calc(100%-2rem)] max-w-sm rounded-lg border bg-background/95 p-4 shadow-[var(--elevation-3)] backdrop-blur"
    >
      <h2 id="resume-call-title" className="font-medium text-sm">
        {t("resume.title")}
      </h2>
      <p id="resume-call-body" className="mt-1 text-muted-foreground text-sm">
        {t("resume.body", { name: resumable.personaName })}
      </p>
      <div className="mt-3 flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={dismissResume}>
          {t("resume.dismiss")}
        </Button>
        <Button size="sm" autoFocus onClick={onResume}>
          {t("resume.confirm")}
        </Button>
      </div>
    </div>
  );
}
