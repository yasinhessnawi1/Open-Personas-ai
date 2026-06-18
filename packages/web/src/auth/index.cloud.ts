/**
 * `@/auth` — cloud (Clerk) client surface (Spec 33).
 *
 * The client-side auth barrel: the `useAuth` token hook + the auth UI
 * components. Selected for `PERSONA_EDITION=cloud` builds via the
 * `turbopack.resolveAlias` in next.config.ts.
 */
export { useAuth } from "@clerk/nextjs";
export { useAccount } from "./account.cloud";
export { ResetPassword } from "./reset-password.cloud";
export { SignIn } from "./sign-in.cloud";
export { SignUp } from "./sign-up.cloud";
export { UserButton } from "./user-button.cloud";
