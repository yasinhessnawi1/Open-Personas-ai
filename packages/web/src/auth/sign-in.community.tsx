/**
 * `SignIn` — community (no-auth) sign-in component (Spec 33).
 *
 * Community has no sign-in wall (single local owner). The route exists but
 * sends the visitor home.
 */
import { redirect } from "next/navigation";

export function SignIn(): never {
  redirect("/");
}
