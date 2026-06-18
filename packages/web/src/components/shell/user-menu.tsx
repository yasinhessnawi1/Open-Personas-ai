"use client";

import { useEffect, useState } from "react";
import { UserButton } from "@/auth";

/**
 * Client-only Clerk `<UserButton />`.
 *
 * Clerk injects the user-avatar markup (`<div data-clerk-component="UserButton">`)
 * on the client after mount, which does not exist in the server-rendered HTML —
 * a hydration mismatch (the warning seen on every `(app)` page). Render a sized
 * placeholder on the server AND the first client paint so the two trees match,
 * then swap in the real button after mount (a normal post-hydration update).
 */
export function UserMenu(): React.JSX.Element {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return <div className="size-7 rounded-full bg-muted" aria-hidden />;
  }
  return <UserButton />;
}
