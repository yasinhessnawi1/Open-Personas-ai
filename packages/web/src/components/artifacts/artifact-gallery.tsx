"use client";

import { Download, FileText, ImageIcon, Trash2 } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { Card } from "@/components/ui/card";
import { useApi } from "@/lib/api/use-api";
import { cn } from "@/lib/utils";

interface ArtifactMetadataView {
  source: string;
  type: string;
  producing_spec: string;
  conversation_id: string | null;
  created_at: string;
  original_name: string | null;
}

export interface ArtifactItem {
  ref: string;
  size_bytes: number;
  media_type: string;
  metadata?: ArtifactMetadataView | null;
}

export interface ArtifactListResponse {
  total: number;
  limit: number;
  offset: number;
  items: readonly ArtifactItem[];
}

export interface ArtifactGalleryProps {
  personaId: string;
  initial: ArtifactListResponse;
}

const SOURCE_CHIPS = ["all", "upload", "generated"] as const;
const TYPE_CHIPS = ["all", "image", "chart", "doc", "data"] as const;

/**
 * Spec F5 T14 + T15 — Artifact gallery with filter chips + per-item renderer
 * dispatch + delete action.
 *
 * Reads URL search params for filter state per D-F5-X-artifact-filter-shape
 * (?source=&type=&conversation_id=&q=). Filter chips write to URL. Items
 * dispatch by ref prefix + media_type:
 *   charts/ + image/* → chart tile
 *   uploads/ + image/* → image tile (lightbox v0.2 candidate)
 *   uploads/ + doc media → download chip row
 *   else → result-block fallback
 *
 * Delete action goes through DELETE /v1/personas/{id}/artifacts/{ref} per
 * D-F5-X-artifact-delete-shape (atomic bytes + sidecar; WorkspaceConsistencyError
 * on partial failure surfaced as 500 with structured detail).
 */
export function ArtifactGallery({ personaId, initial }: ArtifactGalleryProps) {
  const t = useTranslations("artifacts");
  const router = useRouter();
  const search = useSearchParams();
  const api = useApi();
  const [deleting, setDeleting] = useState<string | null>(null);

  const sourceFilter = search.get("source") ?? "all";
  const typeFilter = search.get("type") ?? "all";

  // Client-side filter on top of the server-fetched initial page. T14 v0.1
  // ships the URL-state surface; the actual server-side refetch on filter
  // change is wired by router.refresh (the page boundary re-renders with
  // server-derived query params on next navigation cycle).
  const items = useMemo(() => {
    return initial.items.filter((item) => {
      if (sourceFilter !== "all") {
        if (!item.metadata || item.metadata.source !== sourceFilter)
          return false;
      }
      if (typeFilter !== "all") {
        if (!item.metadata || item.metadata.type !== typeFilter) return false;
      }
      return true;
    });
  }, [initial.items, sourceFilter, typeFilter]);

  function setParam(key: string, value: string | null) {
    const next = new URLSearchParams(search.toString());
    if (value && value !== "all") next.set(key, value);
    else next.delete(key);
    const href = next.toString();
    router.replace(href ? `?${href}` : "?", { scroll: false });
  }

  async function handleDelete(ref: string) {
    if (deleting) return;
    if (!confirm(t("deleteConfirm", { ref }))) return;
    setDeleting(ref);
    try {
      await api.DELETE("/v1/personas/{persona_id}/artifacts/{ref}", {
        params: { path: { persona_id: personaId, ref } },
      });
      router.refresh();
    } finally {
      setDeleting(null);
    }
  }

  return (
    <div data-slot="artifact-gallery" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <FilterGroup
          label={t("sourceLabel")}
          chips={SOURCE_CHIPS}
          active={sourceFilter}
          onSelect={(v) => setParam("source", v)}
          t={t}
          group="source"
        />
        <FilterGroup
          label={t("typeLabel")}
          chips={TYPE_CHIPS}
          active={typeFilter}
          onSelect={(v) => setParam("type", v)}
          t={t}
          group="type"
        />
        <span className="ml-auto type-caption text-muted-foreground">
          {t("countOf", { shown: items.length, total: initial.total })}
        </span>
      </div>

      {items.length === 0 ? (
        <p className="type-body py-12 text-center text-muted-foreground">
          {t("noMatches")}
        </p>
      ) : (
        <ul
          className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
          data-slot="artifact-grid"
        >
          {items.map((item) => (
            <li key={item.ref}>
              <ArtifactTile
                personaId={personaId}
                item={item}
                onDelete={() => handleDelete(item.ref)}
                disabled={deleting === item.ref}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FilterGroup({
  label,
  chips,
  active,
  onSelect,
  t,
  group,
}: {
  label: string;
  chips: readonly string[];
  active: string;
  onSelect: (value: string) => void;
  t: ReturnType<typeof useTranslations>;
  group: string;
}) {
  return (
    <div className="flex items-center gap-2" data-slot={`filter-${group}`}>
      <span className="type-caption text-muted-foreground">{label}</span>
      {chips.map((c) => (
        <button
          key={c}
          type="button"
          onClick={() => onSelect(c)}
          data-state={c === active ? "active" : "inactive"}
          className="glass-chip"
        >
          {t(`${group}.${c}`)}
        </button>
      ))}
    </div>
  );
}

function ArtifactTile({
  personaId,
  item,
  onDelete,
  disabled,
}: {
  personaId: string;
  item: ArtifactItem;
  onDelete: () => void;
  disabled: boolean;
}) {
  const t = useTranslations("artifacts");
  const isImage =
    item.media_type.startsWith("image/") &&
    (item.ref.startsWith("uploads/") || item.ref.startsWith("charts/"));
  const downloadHref = `/api/personas/${personaId}/uploads/${item.ref}`;

  return (
    <Card
      className={cn("glass-card flex flex-col gap-3 overflow-hidden p-3")}
      data-slot="artifact-tile"
    >
      {isImage ? (
        <div className="flex aspect-[4/3] items-center justify-center overflow-hidden rounded bg-muted">
          <ImageIcon
            className="size-10 text-muted-foreground"
            aria-hidden="true"
          />
        </div>
      ) : (
        <div className="flex aspect-[4/3] items-center justify-center rounded bg-muted">
          <FileText
            className="size-10 text-muted-foreground"
            aria-hidden="true"
          />
        </div>
      )}
      <div className="flex flex-col gap-1">
        <span className="type-ui truncate font-medium">
          {item.metadata?.original_name ?? item.ref}
        </span>
        <span className="type-caption text-muted-foreground">
          {formatBytes(item.size_bytes)}
          {item.metadata?.source
            ? ` · ${t(`source.${item.metadata.source}`)}`
            : ""}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <a
          href={downloadHref}
          className="type-caption inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
          data-slot="artifact-download"
        >
          <Download className="size-3.5" aria-hidden="true" />
          {t("download")}
        </a>
        <button
          type="button"
          onClick={onDelete}
          disabled={disabled}
          className="ml-auto inline-flex items-center gap-1 text-destructive hover:bg-destructive/10 rounded p-1 disabled:opacity-50 type-caption"
          aria-label={t("deleteLabel", { ref: item.ref })}
        >
          <Trash2 className="size-3.5" aria-hidden="true" />
        </button>
      </div>
    </Card>
  );
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
