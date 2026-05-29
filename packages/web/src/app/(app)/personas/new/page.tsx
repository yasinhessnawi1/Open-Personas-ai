import { AuthorWizard } from "@/components/personas/author-wizard";
import { type ToolSummary, unwrap } from "@/lib/api";
import { serverApi } from "@/lib/api/server";

// The marquee authoring flow (T08): NL → frontier author → form ⇄ Monaco YAML.
export default async function NewPersonaPage() {
  const api = await serverApi();
  const [tools, skills] = await Promise.all([
    unwrap(await api.GET("/v1/tools")),
    unwrap(await api.GET("/v1/skills")),
  ]);

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6">
      <AuthorWizard
        tools={(tools as ToolSummary[]).map((x) => x.name)}
        skills={(skills as ToolSummary[]).map((x) => x.name)}
      />
    </div>
  );
}
