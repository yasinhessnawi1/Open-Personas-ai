import { cn } from "@/lib/utils";

// The wordmark: a vermilion mark + "Open Persona" in the Fraunces display face.
// Brand name is a proper noun — intentionally not run through i18n.
export function Brand({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <span className="grid size-7 shrink-0 place-items-center rounded-md bg-primary font-heading text-lg leading-none text-primary-foreground">
        P
      </span>
      <span className="font-heading text-lg font-semibold tracking-tight">
        Open Persona
      </span>
    </span>
  );
}
