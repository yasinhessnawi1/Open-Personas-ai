import { ResetPassword } from "@/auth";

/**
 * Password-reset route. The cloud edition renders the branded forgot/reset
 * flow; community redirects home. The branded shell centres itself on the
 * canvas, matching the sign-in / sign-up pages.
 */
export default function ResetPasswordPage() {
  return (
    <main className="flex flex-1 items-center justify-center p-6">
      <ResetPassword />
    </main>
  );
}
