import { FolderArchive } from "lucide-react";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { ArtifactGallery } from "@/components/artifacts/artifact-gallery";
import { PageBody, PageHeader } from "@/components/layout";
import { EmptyState } from "@/components/patterns/empty-state";
import { unwrap } from "@/lib/api";
import { serverApi } from "@/lib/api/server";
import { parsePersonaYaml } from "@/lib/persona";

/**
 * Spec F5 T14 — Artifact view route + initial data load.
 *
 * Per-persona route per D-F5-X-artifact-view-route-location lean (workspace
 * tree matches; cleaner RLS; "files-live-with-persona" discoverability).
 *
 * Server-renders the first page of artifacts; the `<ArtifactGallery>` client
 * island takes over for filter chips + URL state per D-F5-X-artifact-filter-
 * shape and pagination (`useInfiniteQuery` per D-F5-X-artifact-list-pagination).
 */
export default async function PersonaFilesPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const t = await getTranslations("artifacts");
  const api = await serverApi();

  const detailRes = await api.GET("/v1/personas/{persona_id}", {
    params: { path: { persona_id: id } },
  });
  if (detailRes.response.status === 404) notFound();
  const detail = await unwrap(detailRes);
  const p = parsePersonaYaml(detail.yaml);

  // Defence: the artifact endpoint is a Phase 5 addition. If the API
  // process hasn't reloaded with the new route OR the persona workspace
  // is empty, fall back to an empty list rather than throwing — the
  // empty-state surface is the honest UX for both shapes.
  const listRes = await api.GET("/v1/personas/{persona_id}/artifacts", {
    params: { path: { persona_id: id } },
  });
  const initialList =
    listRes.response.ok && listRes.data
      ? listRes.data
      : { total: 0, limit: 50, offset: 0, items: [] };

  return (
    <PageBody>
      <PageHeader
        title={t("titleFor", { name: p.name })}
        subtitle={t("subtitle")}
      />
      {initialList.total === 0 ? (
        <EmptyState
          icon={<FolderArchive className="size-8" aria-hidden="true" />}
          title={t("empty")}
          description={t("emptyHint")}
        />
      ) : (
        <ArtifactGallery personaId={id} initial={initialList} />
      )}
    </PageBody>
  );
}
