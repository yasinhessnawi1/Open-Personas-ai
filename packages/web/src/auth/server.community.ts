/**
 * `@/auth/server` — community (no-auth) server surface (Spec 33).
 *
 * Returns the fixed local owner. `auth().userId` is always set (the signed-in
 * branch is always taken — there is no sign-in wall), and `getToken` returns
 * null (the community API verifies no token).
 */
import "server-only";

import type { CurrentUser, ServerAuth } from "./types";

const LOCAL_OWNER_ID = "local-owner";
const LOCAL_OWNER_EMAIL = "local@localhost";

export async function auth(): Promise<ServerAuth> {
  return { userId: LOCAL_OWNER_ID, getToken: async () => null };
}

export async function currentUser(): Promise<CurrentUser> {
  return {
    primaryEmailAddress: { emailAddress: LOCAL_OWNER_EMAIL },
    firstName: "Local",
    lastName: "Owner",
  };
}
