"use client";

import { ArrowUp } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { buttonVariants } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useChat } from "@/lib/hooks/use-chat";
import { cn } from "@/lib/utils";
import type { ChatMessageView } from "./message-bubble";
import { MessageBubble } from "./message-bubble";

export function ChatWindow({
  conversationId,
  personaName,
  initialMessages,
}: {
  conversationId: string;
  personaName: string;
  initialMessages: ChatMessageView[];
}) {
  const t = useTranslations("chat");
  const { messages, streaming, error, send } = useChat(
    conversationId,
    initialMessages,
  );
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  // biome-ignore lint/correctness/useExhaustiveDependencies: scroll on new messages
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function submit() {
    const value = input.trim();
    if (!value || streaming) return;
    setInput("");
    void send(value);
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-2xl flex-col gap-5 px-4 py-6">
          {messages.length === 0 ? (
            <p className="py-10 text-center text-sm text-muted-foreground">
              {t("empty")}
            </p>
          ) : null}
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}
          {error ? (
            <p className="text-sm text-destructive">{t("error")}</p>
          ) : null}
          <div ref={endRef} />
        </div>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="border-t bg-background/80 backdrop-blur"
      >
        <div className="mx-auto flex w-full max-w-2xl items-end gap-2 px-4 py-3">
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder={t("placeholder", { name: personaName })}
            rows={1}
            className="max-h-40 min-h-10 flex-1 resize-none field-sizing-content"
          />
          <button
            type="submit"
            disabled={streaming || !input.trim()}
            aria-label={t("send")}
            className={cn(buttonVariants({ size: "icon" }))}
          >
            <ArrowUp className="size-4" />
          </button>
        </div>
      </form>
    </div>
  );
}
