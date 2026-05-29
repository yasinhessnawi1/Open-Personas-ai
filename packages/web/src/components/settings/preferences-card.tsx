"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTranslations } from "next-intl";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { LOCALE_COOKIE } from "@/i18n/config";
import { TIER_BADGE_SETTING, useBoolSetting } from "@/lib/hooks/use-setting";
import { cn } from "@/lib/utils";

const THEMES = [
  { value: "light", icon: Sun },
  { value: "dark", icon: Moon },
  { value: "system", icon: Monitor },
] as const;

export function PreferencesCard() {
  const t = useTranslations("settings");
  const tTheme = useTranslations("theme");
  const { theme, setTheme } = useTheme();
  const [tierVisible, setTierVisible] = useBoolSetting(
    TIER_BADGE_SETTING,
    true,
  );
  // next-themes resolves the active theme only on the client; gate the active
  // state on mount so SSR and first client render agree (no hydration warning).
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  return (
    <Card className="gap-4 p-5">
      <h2 className="font-heading text-sm font-semibold tracking-wide text-muted-foreground uppercase">
        {t("preferences")}
      </h2>

      <Row label={t("theme")} hint={t("themeHint")}>
        <div className="flex gap-1 rounded-md border p-0.5">
          {THEMES.map(({ value, icon: Icon }) => {
            const active = mounted && theme === value;
            return (
              <button
                key={value}
                type="button"
                onClick={() => setTheme(value)}
                aria-pressed={active}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-xs",
                  active
                    ? "bg-secondary text-secondary-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                <Icon className="size-3.5" />
                {tTheme(value)}
              </button>
            );
          })}
        </div>
      </Row>

      <Row label={t("tierBadges")} hint={t("tierBadgesHint")}>
        <Switch
          checked={tierVisible}
          onChange={setTierVisible}
          label={t("tierBadges")}
        />
      </Row>

      <Row label={t("language")} hint={t("languageHint")}>
        <LanguageToggle mounted={mounted} />
      </Row>
    </Card>
  );
}

function LanguageToggle({ mounted }: { mounted: boolean }) {
  const t = useTranslations("settings");
  const current =
    mounted && document.cookie.includes(`${LOCALE_COOKIE}=xx`) ? "xx" : "en";
  const choose = (value: "en" | "xx") => {
    // biome-ignore lint/suspicious/noDocumentCookie: document.cookie is the portable write (cookieStore is Chromium-only)
    document.cookie = `${LOCALE_COOKIE}=${value}; path=/; max-age=31536000`;
    window.location.reload();
  };
  const langs = [
    { value: "en", label: t("langEnglish") },
    { value: "xx", label: t("langPseudo") },
  ] as const;
  return (
    <div className="flex gap-1 rounded-md border p-0.5">
      {langs.map(({ value, label }) => (
        <button
          key={value}
          type="button"
          onClick={() => choose(value)}
          aria-pressed={current === value}
          className={cn(
            "rounded px-2.5 py-1 text-xs",
            current === value
              ? "bg-secondary text-secondary-foreground"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function Row({
  label,
  hint,
  children,
}: {
  label: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="min-w-0">
        <p className="text-sm font-medium">{label}</p>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </div>
      {children}
    </div>
  );
}

function Switch({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative h-6 w-10 shrink-0 rounded-full border transition-colors",
        checked ? "bg-primary" : "bg-muted",
      )}
    >
      <span
        className={cn(
          "absolute top-0.5 size-4 rounded-full bg-background transition-all",
          checked ? "left-[1.125rem]" : "left-0.5",
        )}
      />
    </button>
  );
}
