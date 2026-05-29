"use server";

import { redirect } from "next/navigation";
import { serverApi } from "@/lib/api/server";

interface PydanticError {
  msg?: string;
}

function formatDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as PydanticError;
    if (typeof first.msg === "string") return first.msg;
  }
  return fallback;
}

/**
 * Persist an edited persona YAML (PATCH, re-validated server-side) and redirect
 * to its detail page (T08). Returns a structured error on validation failure so
 * the editor can surface it instead of crashing (redirect only on success).
 */
export async function savePersona(
  personaId: string,
  yaml: string,
): Promise<{ error: string } | undefined> {
  const api = await serverApi();
  const res = await api.PATCH("/v1/personas/{persona_id}", {
    params: { path: { persona_id: personaId } },
    body: { yaml },
  });
  if (res.error !== undefined) {
    const body = res.error as { error?: string; detail?: unknown };
    return {
      error: formatDetail(body.detail, body.error ?? "save_failed"),
    };
  }
  redirect(`/personas/${personaId}`);
}
