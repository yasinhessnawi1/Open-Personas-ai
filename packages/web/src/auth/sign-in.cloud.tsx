/**
 * `SignIn` — cloud (Clerk) sign-in component (Spec 33).
 *
 * The cloud sign-in surface. Kept as a clean seam so Spec 34's branded
 * Clerk-Elements page drops straight in here (rebrand this component body)
 * without touching the route page or the community variant.
 */
import { SignIn as ClerkSignIn } from "@clerk/nextjs";

export function SignIn() {
  return <ClerkSignIn />;
}
