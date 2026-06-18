import { SignIn } from "@/auth";

/**
 * Sign-in route. The cloud edition renders the branded Clerk flow; community
 * redirects home. The branded shell is a self-contained split card with its own
 * brand panel + logo lockup, so the page only centres it on the canvas.
 */
export default function SignInPage() {
  return (
    <main className="flex flex-1 items-center justify-center p-6">
      <SignIn />
    </main>
  );
}
