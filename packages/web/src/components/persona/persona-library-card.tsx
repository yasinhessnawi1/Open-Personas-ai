"use client";

import { MoreVertical } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";
import {
  PersonaCard,
  type PersonaCardPersona,
} from "@/components/persona/persona-card";
import { buttonVariants } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useApi } from "@/lib/api/use-api";
import { renameInIdentity } from "@/lib/persona";
import { cn } from "@/lib/utils";

/**
 * Spec F5 T09 — Persona library card wrapper.
 *
 * Composes the F2 `<PersonaCard>` with:
 *   1. The Phase 4-locked glass aesthetic (via the F1-amended `.glass-card`
 *      utility added in T08; D-F5-X-glass-token-f1-amendment).
 *   2. An action `<DropdownMenu>` (kebab top-right) per D-F5-X-persona-library-
 *      design-language: View / Edit / Duplicate / Delete. `<Sheet>`-based
 *      confirmations for Duplicate + Delete are wired here as a v0.1
 *      simple-confirm pattern (the richer F2 `<Sheet>` confirmation flow
 *      per D-F5-X-persona-duplicate-flow lands at T11 — this T09 ships the
 *      structural surface so the page extension is observable end-to-end).
 *
 * F5-local at v0.1; promotes to F2 on second-consumer per the strangler-fig
 * discipline (mirrors D-F3-X-chip-placement / D-F4-X-result-block-placement).
 */
export interface PersonaLibraryCardProps {
  persona: PersonaCardPersona;
}

export function PersonaLibraryCard({ persona }: PersonaLibraryCardProps) {
  const t = useTranslations("personas");
  const router = useRouter();
  const api = useApi();
  const [busy, setBusy] = useState(false);

  async function handleDuplicate() {
    if (busy) return;
    if (!confirm(t("library.duplicateConfirm", { name: persona.name }))) return;
    setBusy(true);
    try {
      // Fetch the original persona's full YAML, mutate identity.name to add
      // " (copy)", and POST as a new persona per D-F5-4 (definition-only:
      // identity / self_facts / worldview / constraints / tools / skills
      // carry; persona_id resets server-side; memory + conversations fresh).
      const original = await api.GET("/v1/personas/{persona_id}", {
        params: { path: { persona_id: persona.id } },
      });
      if (!original.data) return;
      const newYaml = renameInIdentity(
        original.data.yaml,
        `${persona.name} (copy)`,
      );
      await api.POST("/v1/personas", {
        body: { yaml: newYaml, avatar_url: null },
      });
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (busy) return;
    if (!confirm(t("library.deleteConfirm", { name: persona.name }))) return;
    setBusy(true);
    try {
      await api.DELETE("/v1/personas/{persona_id}", {
        params: { path: { persona_id: persona.id } },
      });
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative">
      <PersonaCard
        persona={persona}
        href={`/personas/${persona.id}`}
        className="glass-card"
      />
      <div className="absolute top-2 right-2">
        <DropdownMenu>
          <DropdownMenuTrigger
            aria-label={t("library.menuLabel", { name: persona.name })}
            className={cn(
              buttonVariants({ variant: "ghost", size: "icon" }),
              "size-8",
            )}
            data-slot="persona-library-card-menu"
            onClick={(e) => {
              // Stop propagation so the wrapping <Link> in PersonaCard
              // doesn't navigate when the menu trigger is clicked.
              e.stopPropagation();
              e.preventDefault();
            }}
          >
            <MoreVertical className="size-4" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              render={<Link href={`/personas/${persona.id}`} />}
            >
              {t("library.view")}
            </DropdownMenuItem>
            <DropdownMenuItem
              render={<Link href={`/personas/${persona.id}/edit`} />}
            >
              {t("library.edit")}
            </DropdownMenuItem>
            <DropdownMenuItem disabled={busy} onClick={handleDuplicate}>
              {t("library.duplicate")}
            </DropdownMenuItem>
            <DropdownMenuItem
              disabled={busy}
              variant="destructive"
              onClick={handleDelete}
            >
              {t("library.delete")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}
