"use client";

import { Play } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useFormStatus } from "react-dom";
import { buttonVariants } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

function SubmitButton({ disabled }: { disabled: boolean }) {
  const { pending } = useFormStatus();
  const t = useTranslations("runs");
  return (
    <button
      type="submit"
      disabled={pending || disabled}
      className={cn(buttonVariants(), "gap-2")}
    >
      <Play className="size-4" />
      {pending ? t("starting") : t("start")}
    </button>
  );
}

// The start-run entry from a persona's detail page: a task brief → server action
// → POST /v1/personas/:id/runs → redirect to /runs/:id (T07).
export function StartRunForm({
  action,
  name,
}: {
  action: (formData: FormData) => void | Promise<void>;
  name: string;
}) {
  const t = useTranslations("runs");
  const [task, setTask] = useState("");
  return (
    <form action={action} className="flex flex-col gap-3">
      <Textarea
        name="task"
        value={task}
        onChange={(e) => setTask(e.target.value)}
        rows={2}
        placeholder={t("taskPlaceholder", { name })}
        className="min-h-16 resize-none field-sizing-content"
      />
      <div className="flex justify-end">
        <SubmitButton disabled={!task.trim()} />
      </div>
    </form>
  );
}
