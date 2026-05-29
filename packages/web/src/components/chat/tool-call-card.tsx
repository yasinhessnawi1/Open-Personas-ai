"use client";

import { ChevronRight, Wrench } from "lucide-react";
import { useTranslations } from "next-intl";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

// One tool round in the chat stream: the call (name + args) and, once it lands,
// the result. Collapsed by default (transparency without noise — spec §4.1).
export interface ToolEntry {
  toolName: string;
  args?: Record<string, unknown>;
  result?: string;
  isError?: boolean;
  pending: boolean;
}

export function ToolCallCard({ entry }: { entry: ToolEntry }) {
  const t = useTranslations("chat");
  const hasBody =
    (entry.args && Object.keys(entry.args).length > 0) ||
    entry.result !== undefined;
  return (
    <Collapsible className="group/tool w-fit max-w-full rounded-md border bg-muted/40">
      <CollapsibleTrigger
        disabled={!hasBody}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left font-mono text-xs"
      >
        <Wrench
          className={cn(
            "size-3.5 shrink-0",
            entry.pending
              ? "animate-pulse text-primary"
              : "text-muted-foreground",
          )}
        />
        <span className="truncate">
          {t("toolUsing", { tool: entry.toolName })}
        </span>
        {entry.isError ? (
          <span className="text-destructive">· {t("toolError")}</span>
        ) : null}
        {hasBody ? (
          <ChevronRight className="ml-1 size-3.5 shrink-0 text-muted-foreground transition-transform group-data-[panel-open]/tool:rotate-90" />
        ) : null}
      </CollapsibleTrigger>
      {hasBody ? (
        <CollapsibleContent className="border-t px-3 py-2 font-mono text-xs">
          {entry.args && Object.keys(entry.args).length > 0 ? (
            <pre className="overflow-x-auto whitespace-pre-wrap text-muted-foreground">
              {JSON.stringify(entry.args, null, 2)}
            </pre>
          ) : null}
          {entry.result !== undefined ? (
            <pre
              className={cn(
                "mt-2 overflow-x-auto whitespace-pre-wrap",
                entry.isError ? "text-destructive" : "text-foreground",
              )}
            >
              {entry.result}
            </pre>
          ) : null}
        </CollapsibleContent>
      ) : null}
    </Collapsible>
  );
}
