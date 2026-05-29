import { ArrowLeft, MessageSquare, Pencil, Shield } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { StartRunForm } from "@/components/personas/start-run-form";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { unwrap } from "@/lib/api";
import { serverApi } from "@/lib/api/server";
import { parsePersonaYaml, personaInitials } from "@/lib/persona";
import { cn } from "@/lib/utils";
import { startChat, startRun } from "./actions";

export default async function PersonaDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params; // Next 16: params is async.
  const t = await getTranslations("personas");
  const api = await serverApi();
  const res = await api.GET("/v1/personas/{persona_id}", {
    params: { path: { persona_id: id } },
  });
  if (res.response.status === 404) notFound();
  const detail = await unwrap(res);
  const p = parsePersonaYaml(detail.yaml);

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6">
      <Link
        href="/personas"
        className="mb-6 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        {t("backToList")}
      </Link>

      <header className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-center gap-4">
          <Avatar className="size-14 shrink-0">
            {detail.avatar_url ? (
              <AvatarImage src={detail.avatar_url} alt="" />
            ) : null}
            <AvatarFallback className="bg-primary/10 font-heading text-lg font-medium text-primary">
              {personaInitials(p.name)}
            </AvatarFallback>
          </Avatar>
          <div>
            <h1 className="font-heading text-3xl leading-tight font-semibold tracking-tight">
              {p.name}
            </h1>
            <p className="text-muted-foreground">{p.role}</p>
            <Badge
              variant="secondary"
              className="mt-2 font-mono text-xs uppercase"
            >
              {p.languageDefault}
            </Badge>
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
          <form action={startChat.bind(null, id)}>
            <button type="submit" className={cn(buttonVariants(), "gap-2")}>
              <MessageSquare className="size-4" />
              {t("startChat")}
            </button>
          </form>
          <Link
            href={`/personas/${id}/edit`}
            className={cn(buttonVariants({ variant: "outline" }), "gap-2")}
          >
            <Pencil className="size-4" />
            {t("edit")}
          </Link>
        </div>
      </header>

      <div className="mt-8 flex flex-col gap-5">
        <Card className="gap-3 border-primary/20 p-5">
          <h2 className="font-heading text-sm font-semibold tracking-wide text-muted-foreground uppercase">
            {t("runTaskTitle", { name: p.name })}
          </h2>
          <StartRunForm action={startRun.bind(null, id)} name={p.name} />
        </Card>

        {p.background ? (
          <Section title={t("background")}>
            <p className="text-sm leading-relaxed whitespace-pre-line text-muted-foreground">
              {p.background}
            </p>
          </Section>
        ) : null}

        <Section title={t("constraints")}>
          {p.constraints.length === 0 ? (
            <Empty>{t("none")}</Empty>
          ) : (
            <ul className="flex flex-col gap-2">
              {p.constraints.map((c) => (
                <li key={c} className="flex items-start gap-2 text-sm">
                  <Shield className="mt-0.5 size-4 shrink-0 text-primary" />
                  <span>{c}</span>
                </li>
              ))}
            </ul>
          )}
        </Section>

        {p.selfFacts.length > 0 ? (
          <Section title={t("selfFacts")}>
            <ul className="flex flex-col gap-1.5 text-sm">
              {p.selfFacts.map((f) => (
                <li key={f.fact} className="text-muted-foreground">
                  {f.fact}
                </li>
              ))}
            </ul>
          </Section>
        ) : null}

        {p.worldview.length > 0 ? (
          <Section title={t("worldview")}>
            <ul className="flex flex-col gap-2.5 text-sm">
              {p.worldview.map((w) => (
                <li
                  key={w.claim}
                  className="flex flex-wrap items-baseline gap-2"
                >
                  <span>{w.claim}</span>
                  {w.epistemic ? (
                    <Badge
                      variant="outline"
                      className="font-mono text-[0.65rem] uppercase"
                    >
                      {w.epistemic}
                    </Badge>
                  ) : null}
                </li>
              ))}
            </ul>
          </Section>
        ) : null}

        {(p.tools.length > 0 || p.skills.length > 0) && (
          <div className="grid gap-5 sm:grid-cols-2">
            <Section title={t("tools")}>
              <Chips items={p.tools} empty={t("none")} />
            </Section>
            <Section title={t("skills")}>
              <Chips items={p.skills} empty={t("none")} />
            </Section>
          </div>
        )}
      </div>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="gap-3 p-5">
      <h2 className="font-heading text-sm font-semibold tracking-wide text-muted-foreground uppercase">
        {title}
      </h2>
      {children}
    </Card>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-muted-foreground">{children}</p>;
}

function Chips({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) return <Empty>{empty}</Empty>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((i) => (
        <Badge key={i} variant="secondary" className="font-mono text-xs">
          {i}
        </Badge>
      ))}
    </div>
  );
}
