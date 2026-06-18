"use client";

/**
 * `useAccount` — community (no-auth) account surface (Spec 35 D-35-16).
 *
 * Single local owner: no Clerk identity, no sign-out / manage-account actions.
 * The custom `<AccountMenu>` renders the same design degraded to settings +
 * appearance only. Selected for `PERSONA_EDITION=community` builds.
 */

import type { Account } from "./types";

export function useAccount(): Account {
  return {
    name: "",
    email: null,
    imageUrl: null,
    available: false,
  };
}
