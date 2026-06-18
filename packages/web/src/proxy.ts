// Next 16 renamed `middleware.ts` → `proxy.ts`. Spec 33: the proxy HANDLER is
// edition-selected behind `@/auth/middleware` (Clerk in cloud, a passthrough in
// community), wired by the `turbopack.resolveAlias` in next.config.ts.
//
// Two Next 16 proxy-file constraints shape this file:
//   1. `config` (the matcher) must be a statically-analyzable literal HERE — Next
//      refuses a re-exported `config`. The matcher only decides which routes the
//      proxy RUNS on; the community handler is a no-op passthrough, so the cloud
//      matcher is a harmless superset for community and preserves cloud exactly.
//   2. The proxy function must be a local binding Next can statically see — a bare
//      `export { default } from …` re-export is not recognized as the proxy
//      function at build (page-data collection). So we import the edition handler
//      and re-export it as a concrete default binding.
import editionProxy from "@/auth/middleware";

export default editionProxy;

export const config = {
  matcher: [
    // Skip Next internals + static files (unless referenced in a query string).
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // Always run for API routes + Clerk's auto-proxy path.
    "/(api|trpc)(.*)",
    "/__clerk/(.*)",
  ],
};
