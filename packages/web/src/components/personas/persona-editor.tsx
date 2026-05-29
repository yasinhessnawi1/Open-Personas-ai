"use client";

import { Code2, Save } from "lucide-react";
import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import { useCallback, useState } from "react";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { docToYaml, type PersonaDoc, yamlToDoc } from "@/lib/persona-draft";
import { cn } from "@/lib/utils";
import { PersonaForm } from "./persona-form";

// Monaco is lazy + client-only so it never enters the chat-page bundle (D-09-8).
const YAMLEditor = dynamic(() => import("./yaml-editor"), {
  ssr: false,
  loading: () => <Skeleton className="h-[440px] w-full rounded-md" />,
});

type SaveResult = { error: string } | undefined;

/**
 * The shared persona editor (T08): structured form ⇄ Monaco YAML, kept in sync
 * with the parsed object as the single source of truth (D-09-9). A form edit
 * regenerates the YAML; a YAML edit re-parses into the form, and invalid YAML
 * surfaces an error while the form keeps its last valid state (save is blocked
 * until the YAML parses).
 */
export function PersonaEditor({
  initialDoc,
  tools,
  skills,
  onSave,
  saveLabel,
}: {
  initialDoc: PersonaDoc;
  tools: string[];
  skills: string[];
  onSave: (yaml: string) => Promise<SaveResult>;
  saveLabel: string;
}) {
  const t = useTranslations("author");
  const [doc, setDoc] = useState<PersonaDoc>(initialDoc);
  const [yamlText, setYamlText] = useState<string>(() => docToYaml(initialDoc));
  const [yamlError, setYamlError] = useState<string | null>(null);
  const [showYaml, setShowYaml] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const onFormChange = useCallback((next: PersonaDoc) => {
    setDoc(next);
    setYamlText(docToYaml(next));
    setYamlError(null);
  }, []);

  const onYamlChange = useCallback((text: string) => {
    setYamlText(text);
    try {
      setDoc(yamlToDoc(text));
      setYamlError(null);
    } catch (e) {
      setYamlError((e as Error).message);
    }
  }, []);

  async function save() {
    if (saving || yamlError) return;
    setSaving(true);
    setSaveError(null);
    try {
      const result = await onSave(yamlText);
      if (result?.error) setSaveError(result.error);
    } catch {
      setSaveError(t("saveFailed"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <PersonaForm
        doc={doc}
        onChange={onFormChange}
        tools={tools}
        skills={skills}
      />

      <div className="flex flex-col gap-2">
        <button
          type="button"
          onClick={() => setShowYaml((v) => !v)}
          className="inline-flex w-fit items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <Code2 className="size-4" />
          {showYaml ? t("hideRawYaml") : t("editRawYaml")}
        </button>
        {showYaml ? (
          <>
            <YAMLEditor value={yamlText} onChange={onYamlChange} />
            {yamlError ? (
              <p className="text-sm text-destructive">
                {t("yamlInvalid", { error: yamlError })}
              </p>
            ) : null}
          </>
        ) : null}
      </div>

      {/* Spec-10 seam: clarifying questions + refinement land here (D-09-11). */}
      <p className="rounded-md border border-dashed px-3 py-2 text-xs text-muted-foreground">
        {t("refineSoon")}
      </p>

      <div className="flex items-center justify-end gap-3">
        {saveError ? (
          <p className="flex-1 text-sm text-destructive">
            {t("saveError", { error: saveError })}
          </p>
        ) : null}
        <button
          type="button"
          onClick={() => void save()}
          disabled={saving || yamlError !== null}
          className={cn(buttonVariants(), "gap-2")}
        >
          <Save className="size-4" />
          {saving ? t("saving") : saveLabel}
        </button>
      </div>
    </div>
  );
}
