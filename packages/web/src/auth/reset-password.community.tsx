/**
 * `ResetPassword` — community (no-auth) variant (Spec 34).
 *
 * Community has no auth wall (single local owner), so there is no password to
 * reset. The route exists for surface parity but sends the visitor home.
 */
import { redirect } from "next/navigation";

export function ResetPassword(): never {
  redirect("/");
}
