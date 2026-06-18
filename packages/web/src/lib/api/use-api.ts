"use client";

import { useMemo } from "react";
import { useAuth } from "@/auth";
import { createApiClient } from "./client";

const TEMPLATE = process.env.NEXT_PUBLIC_CLERK_JWT_TEMPLATE;

/**
 * A typed API client for Client Components / TanStack Query hooks. Injects the
 * caller's Clerk JWT-template token as `Authorization: Bearer`. Re-created when
 * the Clerk auth context changes. (D-09-1, D-09-2.)
 */
export function useApi() {
  const { getToken } = useAuth();
  return useMemo(
    () =>
      createApiClient(() =>
        getToken(TEMPLATE ? { template: TEMPLATE } : undefined),
      ),
    [getToken],
  );
}
