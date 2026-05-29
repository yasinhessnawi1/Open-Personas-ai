import { notFound } from "next/navigation";
import { ChatWindow } from "@/components/chat/chat-window";
import type { ChatMessageView } from "@/components/chat/message-bubble";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { unwrap } from "@/lib/api";
import { serverApi } from "@/lib/api/server";
import { parsePersonaYaml, personaInitials } from "@/lib/persona";

export default async function ChatPage({
  params,
}: {
  params: Promise<{ conversationId: string }>;
}) {
  const { conversationId } = await params;
  const api = await serverApi();

  const convRes = await api.GET("/v1/conversations/{conversation_id}", {
    params: { path: { conversation_id: conversationId } },
  });
  if (convRes.response.status === 404) notFound();
  const conv = await unwrap(convRes);

  const personaRes = await api.GET("/v1/personas/{persona_id}", {
    params: { path: { persona_id: conv.persona_id } },
  });
  const persona = personaRes.data
    ? parsePersonaYaml(personaRes.data.yaml)
    : null;
  const name = persona?.name ?? conv.title ?? "Persona";
  const constraint = persona?.constraints[0];

  const initialMessages: ChatMessageView[] = conv.messages.map((m) => ({
    id: m.id,
    role: m.role,
    content: m.content,
  }));

  return (
    <div className="flex h-[calc(100svh-3.5rem)] flex-col">
      {/* Identity is visible — you always know who you're talking to (spec §4.1). */}
      <header className="flex items-center gap-3 border-b px-4 py-2.5">
        <Avatar className="size-9 shrink-0">
          {personaRes.data?.avatar_url ? (
            <AvatarImage src={personaRes.data.avatar_url} alt="" />
          ) : null}
          <AvatarFallback className="bg-primary/10 font-heading text-sm font-medium text-primary">
            {personaInitials(name)}
          </AvatarFallback>
        </Avatar>
        <div className="min-w-0">
          <p className="truncate font-heading font-semibold leading-tight">
            {name}
          </p>
          <p className="truncate text-xs text-muted-foreground">
            {persona?.role}
            {constraint ? ` · ${constraint}` : ""}
          </p>
        </div>
      </header>
      <ChatWindow
        conversationId={conversationId}
        personaName={name}
        initialMessages={initialMessages}
      />
    </div>
  );
}
