/**
 * `@/auth/provider` — community (no-auth) app provider (Spec 33).
 *
 * A passthrough: no `<ClerkProvider>`, no Clerk JS, no auth context.
 */
import type { ReactNode } from "react";

export function AuthProvider({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
