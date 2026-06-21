"use client";

/**
 * Spec V7 D-V7-6 — the mic input controls.
 *
 * `<MicControl>` is the mic affordance, mode-aware:
 *   - always-listening → a mute toggle (the V6 behaviour).
 *   - push-to-talk → a hold-to-talk button (press-and-hold to open the mic);
 *     works on touch (mobile equivalent) and pointer. The actual mic suppression
 *     is reconciled in the provider — this just drives `pttHeld`.
 *
 * `<InputModeToggle>` flips between the two modes (persisted). Both bind the
 * hoisted session; neither touches `useVoiceCall`.
 */

import { Hand, Mic, MicOff } from "lucide-react";
import { useTranslations } from "next-intl";
import { useCallSession } from "@/lib/voice/call-session-context";

export function MicControl({
  className,
}: {
  className?: string;
}): React.JSX.Element {
  const t = useTranslations("voice");
  const { inputMode, pttHeld, setPttHeld, state, toggleMute } =
    useCallSession();

  if (inputMode === "ptt") {
    const release = () => setPttHeld(false);
    const isHoldKey = (key: string) => key === " " || key === "Enter";
    return (
      // Pointer/touch = the primary hold path; the keyboard handlers make the
      // button itself hold-to-talk for keyboard users (criterion #7) — Space/Enter
      // down opens the mic, up closes it (repeat ignored so auto-repeat doesn't thrash).
      <button
        type="button"
        className={className}
        aria-label={t("ptt.hold")}
        title={t("ptt.hold")}
        aria-pressed={pttHeld}
        onPointerDown={() => setPttHeld(true)}
        onPointerUp={release}
        onPointerLeave={release}
        onPointerCancel={release}
        onKeyDown={(e) => {
          if (isHoldKey(e.key) && !e.repeat) {
            e.preventDefault();
            setPttHeld(true);
          }
        }}
        onKeyUp={(e) => {
          if (isHoldKey(e.key)) {
            e.preventDefault();
            setPttHeld(false);
          }
        }}
      >
        {pttHeld ? <Mic aria-hidden /> : <MicOff aria-hidden />}
      </button>
    );
  }

  return (
    <button
      type="button"
      className={className}
      onClick={() => void toggleMute()}
      aria-label={state.micActive ? t("mute") : t("unmute")}
      title={state.micActive ? t("mute") : t("unmute")}
      aria-pressed={!state.micActive}
    >
      {state.micActive ? <Mic aria-hidden /> : <MicOff aria-hidden />}
    </button>
  );
}

export function InputModeToggle({
  className,
}: {
  className?: string;
}): React.JSX.Element {
  const t = useTranslations("voice");
  const { inputMode, setInputMode } = useCallSession();
  const ptt = inputMode === "ptt";

  return (
    <button
      type="button"
      className={className}
      onClick={() => setInputMode(ptt ? "always" : "ptt")}
      aria-label={ptt ? t("ptt.toAlways") : t("ptt.toPtt")}
      title={ptt ? t("ptt.toAlways") : t("ptt.toPtt")}
      aria-pressed={ptt}
    >
      <Hand aria-hidden />
    </button>
  );
}
