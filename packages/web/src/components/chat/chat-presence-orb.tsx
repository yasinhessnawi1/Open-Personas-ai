"use client";

/**
 * Spec 35 D-35-7 — the identity presence avatar in the chat header (signature
 * moment #3, lightweight). It IS the persona's identity avatar (so real,
 * auth-served avatars render correctly via <PersonaAvatar>/<AuthedAvatarImage>
 * — the heavy voice particle orb stays in the voice room) wrapped in an
 * identity-coloured ring that PULSES while the persona is live (composing).
 *
 * The "live" signal arrives via a decoupled `chat-streaming` window event
 * dispatched by <ChatWindow>, so the header (above the chat window in the tree)
 * stays in sync without prop-drilling streaming state up through the page.
 */

import { useEffect, useState } from "react";
import {
  type AvatarPersona,
  PersonaAvatar,
} from "@/components/persona/persona-avatar";

/** Dispatched by ChatWindow on each streaming-state change; detail = streaming. */
export const CHAT_STREAMING_EVENT = "chat-streaming";

export function ChatPresenceOrb({ persona }: { persona: AvatarPersona }) {
  const [streaming, setStreaming] = useState(false);

  useEffect(() => {
    const onStreaming = (e: Event) =>
      setStreaming(Boolean((e as CustomEvent<boolean>).detail));
    window.addEventListener(CHAT_STREAMING_EVENT, onStreaming);
    return () => window.removeEventListener(CHAT_STREAMING_EVENT, onStreaming);
  }, []);

  return (
    <span className="v-presence" data-live={streaming ? "true" : "false"}>
      <PersonaAvatar persona={persona} size="md" />
    </span>
  );
}
