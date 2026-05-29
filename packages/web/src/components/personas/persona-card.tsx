import Link from "next/link";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Card } from "@/components/ui/card";
import type { PersonaSummary } from "@/lib/api";
import { personaInitials } from "@/lib/persona";

export function PersonaCard({ persona }: { persona: PersonaSummary }) {
  return (
    <Link href={`/personas/${persona.id}`} className="group block">
      <Card className="flex flex-row items-center gap-4 p-4 transition-colors group-hover:border-primary/40 group-hover:bg-accent/40">
        <Avatar className="size-11 shrink-0">
          {persona.avatar_url ? (
            <AvatarImage src={persona.avatar_url} alt="" />
          ) : null}
          <AvatarFallback className="bg-primary/10 font-heading font-medium text-primary">
            {personaInitials(persona.name)}
          </AvatarFallback>
        </Avatar>
        <div className="min-w-0">
          <p className="truncate font-heading text-lg leading-tight font-semibold">
            {persona.name}
          </p>
          <p className="truncate text-sm text-muted-foreground">
            {persona.role}
          </p>
        </div>
      </Card>
    </Link>
  );
}
