"use client";

import { useCallback } from "react";
import { type PersonaDetail, unwrap } from "@/lib/api";
import { useApi } from "@/lib/api/use-api";

/**
 * The authoring seam (D-09-11). Today `POST /v1/personas/author` generates AND
 * creates the persona immediately, returning a full `PersonaDetail`. Spec 10's
 * draft-before-save + clarifying-questions + refinement loop drops in here
 * (additional methods on this hook) without restructuring the wizard or form.
 */
export function useAuthor() {
  const api = useApi();
  const author = useCallback(
    async (description: string): Promise<PersonaDetail> =>
      unwrap(await api.POST("/v1/personas/author", { body: { description } })),
    [api],
  );
  return { author };
}
