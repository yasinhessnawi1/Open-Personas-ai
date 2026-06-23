/**
 * Branded-auth redirect targets (cloud / Clerk) — framework-free logic.
 *
 * The custom sign-in / sign-up flows (`sign-in.cloud.tsx`, `sign-up.cloud.tsx`)
 * are built on Clerk's Core-3 signal hooks, NOT the prebuilt `<SignIn/>` /
 * `<SignUp/>` widgets. The prebuilt widgets auto-consume
 * `NEXT_PUBLIC_CLERK_SIGN_{IN,UP}_FALLBACK_REDIRECT_URL`; a custom flow does
 * NOT — it must read those env values itself and pass the target to its own
 * post-completion navigation. Before this helper the flows hard-coded `"/"`, so
 * the configured `/personas` fallback was dead config (bug: post-sign-in /
 * post-sign-up never landed on the intended app route).
 *
 * Two callers need the same target:
 *   1. post-completion navigation (after `finalize` sets the active session),
 *   2. the already-signed-in guard (a visitor with a live Clerk session who
 *      lands on `/sign-in` or `/sign-up` is redirected here instead of being
 *      shown a form that would 400 with `session_exists`).
 *
 * Pure + Clerk-free (reads only `process.env`), so it is unit-testable without
 * rendering a Clerk-bound component. It lives under `*.cloud.*` purely so the
 * edition split keeps it out of the community graph (it is never imported there).
 */

/** Where to land after a completed sign-in / an already-signed-in visit to `/sign-in`. */
export const DEFAULT_SIGN_IN_REDIRECT = "/personas";

/** Where to land after a completed sign-up / an already-signed-in visit to `/sign-up`. */
export const DEFAULT_SIGN_UP_REDIRECT = "/personas";

/**
 * Coerce a configured redirect value to a safe in-app path.
 *
 * Only same-origin absolute paths (a single leading `/`, not `//host` and not a
 * scheme) are honoured; anything else (empty, protocol-relative, absolute URL,
 * or whitespace) falls back to {@link fallback}. This keeps a misconfigured or
 * hostile env value from turning the post-auth navigation into an open redirect.
 */
export function safeRedirectPath(
  value: string | undefined,
  fallback: string,
): string {
  const trimmed = value?.trim();
  if (!trimmed) return fallback;
  // Must be an absolute in-app path, not protocol-relative (`//evil.com`) and
  // not a full URL (`https://…`, `javascript:…`).
  if (!trimmed.startsWith("/") || trimmed.startsWith("//")) return fallback;
  if (/^\/[^/]*:/.test(trimmed)) return fallback;
  return trimmed;
}

/** Resolved post-sign-in target (env override → safe path → `/personas`). */
export function signInRedirectTarget(): string {
  return safeRedirectPath(
    process.env.NEXT_PUBLIC_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL,
    DEFAULT_SIGN_IN_REDIRECT,
  );
}

/** Resolved post-sign-up target (env override → safe path → `/personas`). */
export function signUpRedirectTarget(): string {
  return safeRedirectPath(
    process.env.NEXT_PUBLIC_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL,
    DEFAULT_SIGN_UP_REDIRECT,
  );
}
