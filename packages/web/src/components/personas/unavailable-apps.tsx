import { PackageX } from "lucide-react";
import { useTranslations } from "next-intl";
import { Card } from "@/components/ui/card";

/**
 * N3 (MCP-as-apps) Task 5 — graceful tombstones for removed apps.
 *
 * Renders `PersonaDetail.unavailable_mcp_servers` (N2-D-4 surface c): apps the
 * persona had ENABLED that the catalog auto-sync removed. Informational ONLY —
 * the server is gone, so there is NO re-add / enable action (N3-D-9). The live
 * tool path already degrades without crashing; this is the owner-visible signal
 * that an enabled capability disappeared, rather than vanishing silently.
 *
 * Renders nothing when the list is empty (the common case) so the persona-detail
 * surface is unchanged unless an app actually went away.
 *
 * Pure + presentational (no I/O) so it is trivially render-testable; the
 * server-component page passes it the already-fetched list. The chooser never
 * double-renders one of these — an out-of-catalog server is absent from the
 * catalog entirely, so only this tombstone represents it.
 */
export function UnavailableApps({ names }: { names: readonly string[] }) {
  const t = useTranslations("apps");
  if (names.length === 0) return null;
  return (
    <Card className="gap-3 p-5" data-slot="persona-detail-unavailable-apps">
      <div>
        <p className="type-caption font-mono text-muted-foreground">
          {t("unavailable.heading")}
        </p>
        <p className="mt-2 max-w-prose type-caption normal-case tracking-normal text-muted-foreground">
          {t("unavailable.note")}
        </p>
      </div>
      <ul className="flex flex-col gap-2">
        {names.map((name) => (
          <li
            key={name}
            className="type-body flex items-start gap-2 text-muted-foreground"
            data-slot="unavailable-app"
          >
            <PackageX
              className="mt-0.5 size-4 shrink-0 text-destructive"
              aria-hidden="true"
            />
            <span>{t("unavailable.tombstone", { name })}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
