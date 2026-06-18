/**
 * `@/auth/middleware` — cloud (Clerk) middleware (Spec 33).
 *
 * The spec-08 `clerkMiddleware` config, unchanged. `src/proxy.ts` (the Next 16
 * middleware file convention) re-exports this. Protected routes are the
 * authenticated (app) group; the auth pages + root `/` stay public.
 */
import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const isProtected = createRouteMatcher([
  "/personas(.*)",
  "/chat(.*)",
  "/runs(.*)",
  "/conversations(.*)",
  "/settings(.*)",
]);

export default clerkMiddleware(async (auth, req) => {
  if (isProtected(req)) {
    await auth.protect(); // unauthenticated → redirect to sign-in
  }
});

export const config = {
  matcher: [
    // Skip Next internals + static files (unless referenced in a query string).
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // Always run for API routes + Clerk's auto-proxy path.
    "/(api|trpc)(.*)",
    "/__clerk/(.*)",
  ],
};
