"use client";

import { useCallback, useEffect, useState } from "react";

const EVENT = "persona:setting";

/**
 * A boolean UI preference persisted to localStorage (D-09-5 — UI-only state, no
 * server round-trip). A custom event keeps every component in the tab in sync
 * (the native `storage` event only fires in *other* tabs). SSR-safe: starts at
 * the default, then reads localStorage on mount (so the badge may flash once).
 */
export function useBoolSetting(
  key: string,
  defaultValue: boolean,
): [boolean, (value: boolean) => void] {
  const [value, setValue] = useState(defaultValue);

  useEffect(() => {
    const read = () => {
      const raw = localStorage.getItem(key);
      if (raw !== null) setValue(raw === "true");
    };
    read();
    const onChange = (e: Event) => {
      if ((e as CustomEvent<string>).detail === key) read();
    };
    window.addEventListener(EVENT, onChange);
    window.addEventListener("storage", read);
    return () => {
      window.removeEventListener(EVENT, onChange);
      window.removeEventListener("storage", read);
    };
  }, [key]);

  const set = useCallback(
    (next: boolean) => {
      setValue(next);
      localStorage.setItem(key, String(next));
      window.dispatchEvent(new CustomEvent(EVENT, { detail: key }));
    },
    [key],
  );

  return [value, set];
}

/** The chat tier-badge visibility preference (spec §4.1 power-user setting). */
export const TIER_BADGE_SETTING = "tierBadgeVisible";
