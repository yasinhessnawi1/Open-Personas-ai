"use client";

/**
 * Spec 35 cluster L (D-35-11) — the notification bell + center.
 *
 * Reads the persistent feed off `useNotify()` and renders a base-ui Popover
 * panel listing the entries (newest first, capped at FEED_CAP in the provider).
 * Opening the panel marks everything read; "Clear all" empties the feed. The
 * trigger carries an unread-count badge. Lives in the sidebar header (desktop)
 * + the mobile header bar so it's reachable in both layouts.
 */

import { Popover } from "@base-ui/react/popover";
import { Bell } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import {
  type NotifyLevel,
  useNotify,
} from "@/components/providers/notification-provider";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Level → dot colour, all token-resolved (no-literals gate). The chart palette
 * carries the only multi-hue status tokens: chart-4 (green/h145), chart-2
 * (amber/h73), chart-3 (blue/h232); errors use the destructive token.
 */
const DOT_BY_LEVEL: Record<NotifyLevel, string> = {
  success: "bg-chart-4",
  error: "bg-destructive",
  warning: "bg-chart-2",
  info: "bg-chart-3",
};

export function NotificationBell({ className }: { className?: string }) {
  const t = useTranslations("notifications");
  const format = useFormatter();
  const { entries, unreadCount, markAllRead, clear } = useNotify();

  return (
    <Popover.Root
      onOpenChange={(open) => {
        if (open) markAllRead();
      }}
    >
      <Popover.Trigger
        render={
          <Button variant="ghost" size="icon-sm" aria-label={t("open")} />
        }
        className={cn("relative", className)}
      >
        <Bell />
        {unreadCount > 0 ? (
          <>
            <span
              aria-hidden
              data-slot="notification-unread"
              className="type-caption -top-0.5 -right-0.5 absolute flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 font-medium text-primary-foreground"
            >
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
            <span className="sr-only">
              {t("unreadLabel", { count: unreadCount })}
            </span>
          </>
        ) : null}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner side="bottom" align="end" sideOffset={8}>
          <Popover.Popup
            data-slot="notification-center"
            className="z-50 flex max-h-[min(28rem,70vh)] w-[min(22rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-xl border bg-popover bg-clip-padding text-popover-foreground shadow-[var(--elevation-3)] transition duration-[var(--motion-duration-fast)] ease-[var(--motion-ease-standard)] data-ending-style:scale-95 data-ending-style:opacity-0 data-starting-style:scale-95 data-starting-style:opacity-0"
          >
            <div className="flex items-center justify-between border-b px-3 py-2">
              <Popover.Title className="font-heading font-medium text-foreground text-sm">
                {t("title")}
              </Popover.Title>
              {entries.length > 0 ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={clear}
                  className="h-7 px-2 text-muted-foreground text-xs"
                >
                  {t("clear")}
                </Button>
              ) : null}
            </div>
            {entries.length === 0 ? (
              <p className="px-3 py-8 text-center text-muted-foreground text-sm">
                {t("empty")}
              </p>
            ) : (
              <ul
                className="flex flex-col overflow-y-auto"
                data-slot="notification-feed"
              >
                {entries.map((e) => (
                  <li
                    key={e.id}
                    className="flex gap-2 border-b px-3 py-2 last:border-b-0"
                    data-slot="notification-entry"
                    data-level={e.level}
                  >
                    <span
                      aria-hidden
                      className={cn(
                        "mt-1.5 size-2 shrink-0 rounded-full",
                        DOT_BY_LEVEL[e.level],
                      )}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-foreground text-sm">
                        {e.title}
                      </p>
                      {e.body ? (
                        <p className="text-muted-foreground text-xs">
                          {e.body}
                        </p>
                      ) : null}
                      <p className="type-caption mt-0.5 text-muted-foreground">
                        {format.relativeTime(e.at, Date.now())}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  );
}
