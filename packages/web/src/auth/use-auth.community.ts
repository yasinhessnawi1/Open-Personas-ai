"use client";

import type { AuthState } from "./types";

/**
 * Community `useAuth`: no Clerk, no token. The API runs no-auth in community, so
 * `getToken` returns null and no `Authorization` header is sent.
 */
export function useAuth(): AuthState {
  return { getToken: async () => null };
}
