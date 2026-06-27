"use server";

import { redirect } from "next/navigation";
import { unwrap } from "@/lib/api";
import { serverApi } from "@/lib/api/server";

// Create a conversation against the persona and jump into the chat (T06).
export async function startChat(personaId: string) {
  const api = await serverApi();
  const conv = await unwrap(
    await api.POST("/v1/personas/{persona_id}/conversations", {
      params: { path: { persona_id: personaId } },
      // V9 (V9-D-3): text-born conversation → origin 'chat' (the immutable
      // birth-marker; the only seam between chat and voice).
      body: { title: "", origin: "chat" },
    }),
  );
  redirect(`/chat/${conv.id}`);
}

// Start an agentic run for a task and jump to the run viewer (T07).
export async function startRun(personaId: string, formData: FormData) {
  const task = String(formData.get("task") ?? "").trim();
  if (!task) return; // empty briefs are a no-op (the form disables submit).
  const api = await serverApi();
  const run = await unwrap(
    await api.POST("/v1/personas/{persona_id}/runs", {
      params: { path: { persona_id: personaId } },
      body: { task },
    }),
  );
  redirect(`/runs/${run.id}`);
}
