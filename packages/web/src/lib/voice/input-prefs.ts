/**
 * Spec V7 D-V7-6 — voice input preferences (pure, localStorage-backed).
 *
 * A per-user, cross-session preference (localStorage, not sessionStorage): the
 * input mode (always-listening vs push-to-talk) and the PTT key. Push-to-talk is
 * the direct fix for the earlier mic-oversensitivity reports — in noisy rooms the
 * mic is open only while held.
 *
 * NOTE (boundary): input-DEVICE selection is intentionally NOT here. Switching the
 * active mic device requires the LiveKit `Room`/`LocalParticipant`, which
 * `useVoiceCall` owns and does not expose — applying a device choice would need a
 * V1–V6 seam (see the close-out forward seams). Mode + key are fully controllable
 * at the session layer, so they ship now.
 */

const KEY = "persona:voice-input-prefs";

/** always = open mic after the greeting (V6 default); ptt = open only while held. */
export type InputMode = "always" | "ptt";

export interface InputPrefs {
  readonly mode: InputMode;
  /** `KeyboardEvent.code` for the hold-to-talk key (desktop enhancement). */
  readonly pttKey: string;
}

export const DEFAULT_INPUT_PREFS: InputPrefs = {
  mode: "always",
  pttKey: "Space",
};

function storage(): Storage | null {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null;
  }
}

/** Read the saved input prefs, falling back to {@link DEFAULT_INPUT_PREFS}. */
export function loadInputPrefs(): InputPrefs {
  const raw = storage()?.getItem(KEY);
  if (!raw) return DEFAULT_INPUT_PREFS;
  try {
    const v = JSON.parse(raw) as Partial<InputPrefs>;
    const mode: InputMode = v.mode === "ptt" ? "ptt" : "always";
    const pttKey =
      typeof v.pttKey === "string" && v.pttKey.length > 0
        ? v.pttKey
        : DEFAULT_INPUT_PREFS.pttKey;
    return { mode, pttKey };
  } catch {
    return DEFAULT_INPUT_PREFS;
  }
}

/** Persist the input prefs (best-effort — quota/private-mode failures are ignored). */
export function saveInputPrefs(prefs: InputPrefs): void {
  try {
    storage()?.setItem(KEY, JSON.stringify(prefs));
  } catch {
    // non-fatal
  }
}
