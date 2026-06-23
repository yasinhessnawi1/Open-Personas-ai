"use client";

/**
 * `useSignedInRedirect` — already-signed-in guard for the branded auth pages
 * (cloud / Clerk).
 *
 * The custom sign-in / sign-up flows are built on Clerk's Core-3 signal hooks,
 * so unlike the prebuilt widgets they do NOT auto-redirect a visitor who already
 * has a live session. Without this guard, a signed-in user who lands on
 * `/sign-in` (e.g. a stale bookmark, a back-navigation, or `afterSignOutUrl`
 * mis-fires) sees the sign-in form and — on submit — gets a `400 session_exists`
 * ("You're already signed in.") because `signIn.create()` cannot start a new
 * attempt while a session is active.
 *
 * This hook subscribes to `useAuth()` (the loaded + isSignedIn reactive signal)
 * and, once Clerk has loaded and reports an active session, replaces the current
 * history entry with the configured in-app target. It returns `redirecting` so
 * the flow can render the calm loading state instead of flashing the form in the
 * brief window before the navigation commits.
 *
 * `router.replace` (not `push`) so the auth page never lands in the back stack;
 * an absolute (cross-origin) configured target falls back through
 * `safeRedirectPath`, so this can only navigate to a same-origin app path.
 */
import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

/**
 * Redirect an already-signed-in visitor away from an auth page.
 *
 * @param target Resolved in-app path to land on (e.g. from `signInRedirectTarget()`).
 * @returns `redirecting` — true once a live session is detected and the
 *   navigation has been issued, so the caller renders a loading state rather
 *   than the form.
 */
export function useSignedInRedirect(target: string): { redirecting: boolean } {
  const { isLoaded, isSignedIn } = useAuth();
  const router = useRouter();
  const [redirecting, setRedirecting] = useState(false);

  useEffect(() => {
    if (isLoaded && isSignedIn) {
      setRedirecting(true);
      router.replace(target);
    }
  }, [isLoaded, isSignedIn, router, target]);

  return { redirecting };
}
