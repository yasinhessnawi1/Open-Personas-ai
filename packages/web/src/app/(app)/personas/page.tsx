import { Sparkles } from "lucide-react";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { PersonaCard } from "@/components/personas/persona-card";
import { buttonVariants } from "@/components/ui/button";
import { unwrap } from "@/lib/api";
import { serverApi } from "@/lib/api/server";
import { cn } from "@/lib/utils";

// Server component: fetches the caller's personas via the generated client
// (server-to-server, no CORS), authed with the Clerk token.
export default async function PersonasPage() {
  const t = await getTranslations("personas");
  const api = await serverApi();
  const personas = await unwrap(await api.GET("/v1/personas"));

  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-8 sm:px-6">
      <header className="mb-6 flex items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl font-semibold tracking-tight">
            {t("title")}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">{t("subtitle")}</p>
        </div>
        <Link href="/personas/new" className={cn(buttonVariants(), "gap-2")}>
          <Sparkles className="size-4" />
          {t("create")}
        </Link>
      </header>

      {personas.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed py-20 text-center">
          <Sparkles className="size-8 text-muted-foreground" />
          <p className="font-heading text-xl font-semibold">{t("empty")}</p>
          <p className="max-w-sm text-sm text-muted-foreground">
            {t("emptyHint")}
          </p>
          <Link
            href="/personas/new"
            className={cn(buttonVariants(), "mt-2 gap-2")}
          >
            <Sparkles className="size-4" />
            {t("create")}
          </Link>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {personas.map((p) => (
            <PersonaCard key={p.id} persona={p} />
          ))}
        </div>
      )}
    </div>
  );
}
