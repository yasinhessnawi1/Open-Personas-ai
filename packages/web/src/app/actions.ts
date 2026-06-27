"use server";

import { redirect } from "next/navigation";
import { unwrap } from "@/lib/api";
import { serverApi } from "@/lib/api/server";

/**
 * Root dashboard quick entry points.
 *
 * Both mirror the persona-detail `startChat` plumbing (create a conversation,
 * then jump in) but differ in destination: text chat vs the voice surface.
 * Voice has no standalone entry — it always hangs off a conversation
 * (`/chat/{id}/voice`), so reaching it from a cold start means minting a
 * conversation first. Co-located with the auth-aware root `/` it serves.
 */

/** Create a conversation against the persona and open text chat. */
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

/** Create a conversation against the persona and open the voice surface. */
export async function startVoice(personaId: string) {
  const api = await serverApi();
  const conv = await unwrap(
    await api.POST("/v1/personas/{persona_id}/conversations", {
      params: { path: { persona_id: personaId } },
      // V9 (V9-D-3 / V9-D-X-marker-writer-web): this server action opens the
      // voice surface, so the conversation is call-born → origin 'call' (excluded
      // from the chat list; surfaces in Calls).
      body: { title: "", origin: "call" },
    }),
  );
  redirect(`/chat/${conv.id}/voice`);
}
