"use client";

import { ChevronDown } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";
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
 * Spec F5 T10 — persona-detail "Manage" action menu.
 *
 * Client island composed into the otherwise-server-rendered persona
 * detail page. Adds Duplicate + Delete actions (per D-F5-4 / D-F5-X-persona-
 * duplicate-flow) + an entry point routing to the Spec 10 authoring flow
 * for richer edits.
 *
 * T11 lands the richer F2 `<Sheet>` confirmation surfaces; T10 ships the
 * structural surface so the detail page extension is observable end-to-end.
 */
export interface PersonaDetailManageMenuProps {
  personaId: string;
  personaName: string;
}

export function PersonaDetailManageMenu({
  personaId,
  personaName,
}: PersonaDetailManageMenuProps) {
  const t = useTranslations("personas");
  const router = useRouter();
  const api = useApi();
  const [busy, setBusy] = useState(false);

  async function handleDuplicate() {
    if (busy) return;
    if (!confirm(t("library.duplicateConfirm", { name: personaName }))) return;
    setBusy(true);
    try {
      // Fetch the original full YAML + mutate identity.name per D-F5-4.
      const original = await api.GET("/v1/personas/{persona_id}", {
        params: { path: { persona_id: personaId } },
      });
      if (!original.data) return;
      const newYaml = renameInIdentity(
        original.data.yaml,
        `${personaName} (copy)`,
      );
      await api.POST("/v1/personas", {
        body: { yaml: newYaml, avatar_url: null },
      });
      router.push("/personas");
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (busy) return;
    if (!confirm(t("library.deleteConfirm", { name: personaName }))) return;
    setBusy(true);
    try {
      await api.DELETE("/v1/personas/{persona_id}", {
        params: { path: { persona_id: personaId } },
      });
      router.push("/personas");
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label={t("detail.manageLabel", { name: personaName })}
        className={cn(buttonVariants({ variant: "outline" }), "gap-2")}
        data-slot="persona-detail-manage"
      >
        {t("detail.manage")}
        <ChevronDown className="size-4" aria-hidden="true" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem
          render={<Link href={`/personas/${personaId}/edit`} />}
        >
          {t("detail.editViaAuthoring")}
        </DropdownMenuItem>
        <DropdownMenuItem
          render={<Link href={`/personas/${personaId}/files`} />}
        >
          {t("detail.files")}
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
  );
}
