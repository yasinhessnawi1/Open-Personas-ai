import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { RunView } from "@/components/runs/run-view";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { unwrap } from "@/lib/api";
import { serverApi } from "@/lib/api/server";
import { parsePersonaYaml, personaInitials } from "@/lib/persona";

export default async function RunPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params; // Next 16: params is async.
  const t = await getTranslations("runs");
  const api = await serverApi();

  const runRes = await api.GET("/v1/runs/{run_id}", {
    params: { path: { run_id: runId } },
  });
  if (runRes.response.status === 404) notFound();
  const run = await unwrap(runRes);

  const personaRes = await api.GET("/v1/personas/{persona_id}", {
    params: { path: { persona_id: run.persona_id } },
  });
  const persona = personaRes.data
    ? parsePersonaYaml(personaRes.data.yaml)
    : null;
  const name = persona?.name ?? "Persona";

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6">
      <Link
        href={`/personas/${run.persona_id}`}
        className="mb-6 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        {t("backToPersona")}
      </Link>

      <header className="flex items-start gap-4">
        <Avatar className="size-12 shrink-0">
          {personaRes.data?.avatar_url ? (
            <AvatarImage src={personaRes.data.avatar_url} alt="" />
          ) : null}
          <AvatarFallback className="bg-primary/10 font-heading font-medium text-primary">
            {personaInitials(name)}
          </AvatarFallback>
        </Avatar>
        <div className="min-w-0">
          <p className="font-mono text-xs tracking-wide text-muted-foreground uppercase">
            {t("runByline", { name })}
          </p>
          <h1 className="mt-1 font-heading text-2xl leading-snug font-semibold tracking-tight">
            {run.task}
          </h1>
        </div>
      </header>

      <div className="mt-8">
        <RunView runId={runId} initial={run} />
      </div>
    </div>
  );
}
