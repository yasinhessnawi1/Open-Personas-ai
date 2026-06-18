/**
 * `SignUp` — community (no-auth) sign-up component (Spec 33).
 *
 * Community has no sign-up (single local owner). The route exists but sends the
 * visitor home.
 */
import { redirect } from "next/navigation";

export function SignUp(): never {
  redirect("/");
}
