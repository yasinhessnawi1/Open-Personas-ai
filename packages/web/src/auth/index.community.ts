/**
 * `@/auth` — community (no-auth) client surface (Spec 33).
 *
 * A Clerk-free stub: `useAuth` mints no token, the auth UI components redirect
 * home / render nothing. Selected for `PERSONA_EDITION=community` builds.
 */

export { SignIn } from "./sign-in.community";
export { SignUp } from "./sign-up.community";
export { useAuth } from "./use-auth.community";
export { UserButton } from "./user-button.community";
