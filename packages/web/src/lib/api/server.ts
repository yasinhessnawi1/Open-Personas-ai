import "server-only";

import { auth } from "@/auth/server";
import { createApiClient } from "./client";

const TEMPLATE = process.env.NEXT_PUBLIC_CLERK_JWT_TEMPLATE;

/**
 * A typed API client for use in Server Components / Server Actions. Injects the
 * caller's Clerk JWT-template token (with the `aud` the API verifies) as
 * `Authorization: Bearer`. (D-09-1, D-09-2.)
 */
export async function serverApi() {
  const { getToken } = await auth();
  return createApiClient(() =>
    getToken(TEMPLATE ? { template: TEMPLATE } : undefined),
  );
}
