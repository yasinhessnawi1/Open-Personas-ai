"use client";

/**
 * Spec V7 D-V7-4 — the end-and-switch confirm.
 *
 * Rendered once in the shell (inside the call-session provider). It appears only
 * when a `pendingSwitch` is set — i.e. the user asked to call someone while a
 * different call is live. Confirming **ends the active call, then starts the
 * pending one (serialized — never two Rooms)** and navigates to the new call's
 * full view; cancelling keeps the current call.
 *
 * A minimal accessible confirm (no new dependency): `role="alertdialog"`,
 * `aria-modal`, labelled + described, Escape / backdrop cancels, the confirm
 * button auto-focuses on open. (The full focus-trap sweep is the close-out a11y
 * task.)
 */

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { useCallSession } from "@/lib/voice/call-session-context";

export function SwitchCallDialog(): React.JSX.Element | null {
  const t = useTranslations("voice");
  const router = useRouter();
  const { pendingSwitch, target, confirmSwitch, cancelSwitch } =
    useCallSession();
  const dialogRef = useRef<HTMLDivElement>(null);

  // Escape cancels (document-level so it works regardless of focus position).
  useEffect(() => {
    if (pendingSwitch === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") cancelSwitch();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [pendingSwitch, cancelSwitch]);

  if (pendingSwitch === null) return null;

  // Contain Tab within the modal (aria-modal) so focus can't slip behind it.
  const trapTab = (e: React.KeyboardEvent) => {
    if (e.key !== "Tab") return;
    const nodes = dialogRef.current?.querySelectorAll<HTMLElement>("button");
    if (!nodes || nodes.length === 0) return;
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };

  const onConfirm = async () => {
    const nextConversationId = pendingSwitch.conversationId;
    await confirmSwitch();
    router.push(`/chat/${nextConversationId}/voice`);
  };

  return (
    // Backdrop is a passive scrim — dismissal is Escape (above) or the Cancel
    // button; we intentionally do NOT close on backdrop click so a call isn't
    // ended by a stray tap (a confirm dialog should require an explicit choice).
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        ref={dialogRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="switch-call-title"
        aria-describedby="switch-call-body"
        onKeyDown={trapTab}
        className="w-full max-w-sm rounded-lg border bg-background p-6 shadow-[var(--elevation-3)]"
      >
        <h2 id="switch-call-title" className="font-medium text-lg">
          {t("switch.title")}
        </h2>
        <p id="switch-call-body" className="mt-2 text-muted-foreground text-sm">
          {t("switch.body", {
            current: target?.personaName ?? "",
            next: pendingSwitch.personaName,
          })}
        </p>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="ghost" onClick={cancelSwitch}>
            {t("switch.cancel")}
          </Button>
          <Button autoFocus onClick={() => void onConfirm()}>
            {t("switch.confirm")}
          </Button>
        </div>
      </div>
    </div>
  );
}
