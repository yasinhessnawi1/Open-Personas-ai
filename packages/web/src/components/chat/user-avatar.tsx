"use client";

/**
 * Spec 35 — the signed-in user's avatar on their own chat turns (mirrors the
 * persona avatar on the other side of the thread). Reads the account from the
 * `@/auth` façade (Clerk image in cloud — a public CDN URL, so a raw <img> is
 * fine; a degraded initials mark in community). Imports no `@clerk/*` itself.
 */

import { useTranslations } from "next-intl";
import { useAccount } from "@/auth";
import { cn } from "@/lib/utils";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function UserAvatar({ className }: { className?: string }) {
  const account = useAccount();
  const t = useTranslations("chat");
  const label = account.name || t("you");

  if (account.imageUrl) {
    return (
      <span
        className={cn(
          "inline-block size-10 overflow-hidden rounded-full",
          className,
        )}
      >
        {/* biome-ignore lint/performance/noImgElement: public Clerk CDN avatar — no auth header, no next/image remote-domain config needed. */}
        <img
          src={account.imageUrl}
          alt={label}
          className="size-full object-cover"
        />
      </span>
    );
  }

  return (
    <span
      className={cn(
        "inline-grid size-10 place-items-center rounded-full bg-secondary type-ui font-medium text-secondary-foreground",
        className,
      )}
      role="img"
      aria-label={label}
    >
      {initials(label)}
    </span>
  );
}
