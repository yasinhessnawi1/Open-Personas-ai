import { MessageSquare } from "lucide-react";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { Card } from "@/components/ui/card";
import { unwrap } from "@/lib/api";
import { serverApi } from "@/lib/api/server";

export default async function ConversationsPage() {
  const t = await getTranslations("conversations");
  const api = await serverApi();
  const conversations = await unwrap(await api.GET("/v1/conversations"));

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6">
      <header className="mb-6">
        <h1 className="font-heading text-3xl font-semibold tracking-tight">
          {t("title")}
        </h1>
        <p className="text-muted-foreground">{t("subtitle")}</p>
      </header>

      {conversations.length === 0 ? (
        <Card className="items-center gap-2 p-10 text-center">
          <MessageSquare className="size-6 text-muted-foreground" />
          <p className="font-heading text-lg font-medium">{t("empty")}</p>
          <p className="text-sm text-muted-foreground">{t("emptyHint")}</p>
        </Card>
      ) : (
        <ul className="flex flex-col gap-2">
          {conversations.map((c) => (
            <li key={c.id}>
              <Link href={`/chat/${c.id}`} className="group block">
                <Card className="flex flex-row items-center gap-3 p-4 transition-colors group-hover:border-primary/40 group-hover:bg-accent/40">
                  <MessageSquare className="size-4 shrink-0 text-muted-foreground" />
                  <span className="min-w-0 flex-1 truncate font-medium">
                    {c.title || t("untitled")}
                  </span>
                  <span className="shrink-0 font-mono text-xs text-muted-foreground">
                    {new Date(c.updated_at).toLocaleDateString()}
                  </span>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
