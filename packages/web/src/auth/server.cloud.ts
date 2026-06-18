/**
 * `@/auth/server` — cloud (Clerk) server surface (Spec 33).
 *
 * The server-side auth functions used by Server Components / Actions: `auth()`
 * (owner id + token getter) and `currentUser()` (profile). Re-exported straight
 * from Clerk — cloud behavior is unchanged.
 */
import "server-only";

export { auth, currentUser } from "@clerk/nextjs/server";
