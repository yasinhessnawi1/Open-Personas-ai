/**
 * `@/auth/middleware` — community (no-auth) middleware (Spec 33).
 *
 * A passthrough: no route protection (single local owner, no sign-in wall). The
 * empty matcher means the middleware never runs.
 */
import { type NextRequest, NextResponse } from "next/server";

export default function middleware(_req: NextRequest): NextResponse {
  return NextResponse.next();
}

export const config = { matcher: [] };
