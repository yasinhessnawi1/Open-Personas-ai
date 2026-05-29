"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Nav } from "./nav";

// Shared inner content for both the desktop sidebar and the mobile sheet.
export function SidebarBody({ onNavigate }: { onNavigate?: () => void }) {
  const t = useTranslations("nav");
  return (
    <div className="flex flex-1 flex-col gap-5">
      <Link
        href="/personas/new"
        onClick={onNavigate}
        className={cn(buttonVariants(), "justify-start gap-2")}
      >
        <Plus className="size-4" />
        {t("newPersona")}
      </Link>
      <Nav onNavigate={onNavigate} />
    </div>
  );
}
