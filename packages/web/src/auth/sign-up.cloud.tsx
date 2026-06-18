/**
 * `SignUp` — cloud (Clerk) sign-up component (Spec 33).
 *
 * The cloud sign-up surface. Clean seam for Spec 34's branded Clerk-Elements
 * page (rebrand this component body); the route page + community stay untouched.
 */
import { SignUp as ClerkSignUp } from "@clerk/nextjs";

export function SignUp() {
  return <ClerkSignUp />;
}
