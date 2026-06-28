import { ArrowLeft, MessageSquare, Pencil, Phone, Shield } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { startVoice } from "@/app/actions";
import { PageBody, Section } from "@/components/layout";
import { MemoryStores } from "@/components/persona/memory-stores";
import { PersonaDetailManageMenu } from "@/components/persona/persona-detail-manage-menu";
import { PersonaIdentityHeaderLive } from "@/components/persona/persona-identity-header-live";
import { StartRunForm } from "@/components/personas/start-run-form";
import { UnavailableApps } from "@/components/personas/unavailable-apps";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { unwrap } from "@/lib/api";
import { serverApi } from "@/lib/api/server";
import { parsePersonaYaml } from "@/lib/persona";
import { cn } from "@/lib/utils";
import { startChat, startRun } from "./actions";

/**
 * Spec F2 T28 — Persona detail screen (rebuilt).
 *
 * Strangler-fig replace of the scaffold's detail JSX.
 *
 * DO NOT TOUCH (per audit.md §personas-detail.plumbing):
 *   - `serverApi()` GET `/v1/personas/{persona_id}` + `parsePersonaYaml(yaml)`
 *     + `notFound()` on 404 (Next 16 async-params contract);
 *   - `./actions.ts` server actions (`startChat`, `startRun`);
 *   - `<StartRunForm>` (composed verbatim from `components/personas/`).
 *
 * REPLACED (presentation only):
 *   - hand-rolled `<header>` with `<Avatar>` + `bg-primary/10` fallback
 *     (the D-F1-5 violation called out in audit.md §personas-detail.plumbing
 *     line 47) → T13 `<PersonaIdentityHeader size="lg">` composing T06
 *     `<PersonaAvatar>` so the avatar fill becomes per-persona identity-coloured;
 *   - hand-rolled `mx-auto max-w-3xl px-… py-…` → T20 `<PageBody>`;
 *   - inline `<Section title>` (Card + uppercase-tracking-wide heading) →
 *     T20 `<Section heading>` wrapping a T04 retokenised `<Card>` body so
 *     the section headings carry F2's Fraunces `.type-heading` voice;
 *   - inline `<Empty>` + `<Chips>` → muted body-text + retokenised `<Badge>`;
 *   - `text-[0.65rem]` epistemic badge (audit.md line 136 violation) →
 *     `.type-caption font-mono uppercase` so the badge resolves through F1's
 *     `--text-caption-*` tokens.
 *
 * The "Run task" callout retains the `border-primary/20` accent (vermilion
 * is the brand cue; this is THE primary CTA on the detail surface).
 */
export default async function PersonaDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const t = await getTranslations("personas");
  const api = await serverApi();
  const res = await api.GET("/v1/personas/{persona_id}", {
    params: { path: { persona_id: id } },
  });
  if (res.response.status === 404) notFound();
  const detail = await unwrap(res);
  const p = parsePersonaYaml(detail.yaml);

  const headerPersona = {
    id: detail.id,
    name: p.name,
    role: p.role,
    avatar_url: detail.avatar_url ?? null,
  };

  return (
    <PageBody width="wide">
      <Link
        href="/personas"
        className="type-ui mb-6 inline-flex items-center gap-1.5 text-muted-foreground hover:text-foreground"
        data-slot="back-link"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        {t("backToList")}
      </Link>

      <header
        className="mb-8 flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between"
        data-slot="persona-detail-header"
      >
        <div className="flex min-w-0 flex-col gap-3">
          <PersonaIdentityHeaderLive persona={headerPersona} size="lg" />
          {p.background ? (
            <p className="max-w-prose type-body text-muted-foreground italic">
              {p.background}
            </p>
          ) : null}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-3">
          <Badge
            variant="secondary"
            className="type-caption font-mono uppercase"
          >
            {p.languageDefault}
          </Badge>
          <form action={startVoice.bind(null, id)}>
            <button
              type="submit"
              className={cn(buttonVariants({ variant: "outline" }), "gap-2")}
            >
              <Phone className="size-4" aria-hidden="true" />
              {t("memory.call")}
            </button>
          </form>
          <form action={startChat.bind(null, id)}>
            <button type="submit" className={cn(buttonVariants(), "gap-2")}>
              <MessageSquare className="size-4" aria-hidden="true" />
              {t("startChat")}
            </button>
          </form>
          <Link
            href={`/personas/${id}/edit`}
            className={cn(buttonVariants({ variant: "outline" }), "gap-2")}
          >
            <Pencil className="size-4" aria-hidden="true" />
            {t("edit")}
          </Link>
          <PersonaDetailManageMenu personaId={id} personaName={p.name} />
        </div>
      </header>

      {/* Spec 35: two-column — typed memory + constraints (main) beside the
          Run-a-task CTA + routing/capabilities (a sticky aside that stays put
          while the memory stores scroll). */}
      <div className="grid gap-6 lg:grid-cols-[1fr_320px] lg:items-start">
        <div
          className="flex min-w-0 flex-col gap-8"
          data-slot="persona-detail-main"
        >
          <Section heading={t("memory.heading")}>
            <MemoryStores
              name={p.name}
              role={p.role}
              language={p.languageDefault}
              selfFacts={p.selfFacts.map((f) => f.fact)}
              worldview={p.worldview}
              conversationCount={detail.conversation_count ?? 0}
            />
          </Section>

          <Section heading={t("constraints")}>
            <Card className="p-5">
              {p.constraints.length === 0 ? (
                <p className="type-body text-muted-foreground">{t("none")}</p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {p.constraints.map((c) => (
                    <li key={c} className="type-body flex items-start gap-2">
                      <Shield
                        className="mt-0.5 size-4 shrink-0 text-primary"
                        aria-hidden="true"
                      />
                      <span>{c}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </Section>
        </div>

        <aside
          className="flex flex-col gap-6 lg:sticky lg:top-4"
          data-slot="persona-detail-aside"
        >
          <Card
            className="gap-3 border-l-2 border-l-primary p-5"
            data-slot="persona-detail-run-task"
          >
            <h2 className="type-heading" data-slot="run-task-title">
              {t("runTaskTitle", { name: p.name })}
            </h2>
            <StartRunForm action={startRun.bind(null, id)} name={p.name} />
          </Card>

          <Card className="gap-5 p-5">
            <div>
              <p className="type-caption font-mono text-muted-foreground">
                {t("detail.routing")}
              </p>
              <p className="mt-2">
                <span className="v-chip">
                  <span
                    className="size-1.5 rounded-full bg-primary"
                    aria-hidden="true"
                  />
                  {t("detail.routingValue")}
                </span>
              </p>
              <p className="mt-2 max-w-prose type-caption normal-case tracking-normal text-muted-foreground">
                {t("detail.routingHint")}
              </p>
            </div>

            <div>
              <p className="type-caption font-mono text-muted-foreground">
                {t("tools")}
              </p>
              {p.tools.length === 0 ? (
                <p className="mt-2 type-ui text-muted-foreground">
                  {t("none")}
                </p>
              ) : (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {p.tools.map((i) => (
                    <Badge
                      key={i}
                      variant="secondary"
                      className="type-caption font-mono"
                    >
                      {i}
                    </Badge>
                  ))}
                </div>
              )}
            </div>

            <div>
              <p className="type-caption font-mono text-muted-foreground">
                {t("skills")}
              </p>
              {p.skills.length === 0 ? (
                <p className="mt-2 type-ui text-muted-foreground">
                  {t("none")}
                </p>
              ) : (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {p.skills.map((i) => (
                    <Badge
                      key={i}
                      variant="secondary"
                      className="type-caption font-mono"
                    >
                      {i}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          </Card>

          {/* N3 (Task 5): graceful tombstones for apps this persona enabled that
              were removed from the catalog (PersonaDetail.unavailable_mcp_servers,
              N2-D-4 surface c). Informational only — NO re-add action (N3-D-9).
              Renders nothing when the list is empty. */}
          <UnavailableApps names={detail.unavailable_mcp_servers ?? []} />
        </aside>
      </div>
    </PageBody>
  );
}
