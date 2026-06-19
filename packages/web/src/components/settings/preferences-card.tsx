"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTranslations } from "next-intl";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { LOCALE_COOKIE } from "@/i18n/config";
import { TIER_BADGE_SETTING, useBoolSetting } from "@/lib/hooks/use-setting";

/**
 * Spec F2 T31 — PreferencesCard (retokenised).
 *
 * DO NOT TOUCH (per audit.md §settings.plumbing):
 *   - `useTheme` + `useBoolSetting(TIER_BADGE_SETTING, true)` + `LOCALE_COOKIE`;
 *   - the `mounted` SSR-gate (no hydration warning);
 *   - the inline `<Switch>` thumb `left-[1.125rem]` positional pixel (the
 *     audit notes it as switch-thumb positional, not a design value).
 *
 * REPLACED:
 *   - section h2 `font-heading text-sm tracking-wide uppercase` →
 *     `.type-caption font-mono uppercase`;
 *   - Row label `text-sm font-medium` → `.type-body font-medium`;
 *   - Row hint `text-xs text-muted-foreground` → `.type-caption text-muted-foreground`;
 *   - Theme/language toggle buttons `text-xs` → `.type-caption`.
 */
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
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  return (
    <Card className="gap-4 p-5" data-slot="settings-preferences">
      <h2 className="type-caption font-mono text-muted-foreground uppercase">
        {t("preferences")}
      </h2>

      <Row label={t("theme")} hint={t("themeHint")}>
        <div className="v-seg">
          {THEMES.map(({ value, icon: Icon }) => {
            const active = mounted && theme === value;
            return (
              <button
                key={value}
                type="button"
                onClick={() => setTheme(value)}
                aria-pressed={active}
                data-active={active ? "true" : undefined}
                className="inline-flex items-center gap-1.5"
                data-slot="settings-theme-option"
              >
                <Icon className="size-3.5" aria-hidden="true" />
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
    // biome-ignore lint/suspicious/noDocumentCookie: portable write (cookieStore is Chromium-only)
    document.cookie = `${LOCALE_COOKIE}=${value}; path=/; max-age=31536000`;
    window.location.reload();
  };
  const langs = [
    { value: "en", label: t("langEnglish") },
    { value: "xx", label: t("langPseudo") },
  ] as const;
  return (
    <div className="v-seg">
      {langs.map(({ value, label }) => (
        <button
          key={value}
          type="button"
          onClick={() => choose(value)}
          aria-pressed={current === value}
          data-active={current === value ? "true" : undefined}
          data-slot="settings-language-option"
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
  // Spec 35: the v1 setting row — title/desc on the left, control on the right,
  // hairline-separated (the last row drops its rule against the card padding).
  return (
    <div className="v-set-row last:border-b-0">
      <div className="min-w-0">
        <div className="v-set-row__t">{label}</div>
        <div className="v-set-row__d">{hint}</div>
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
  // Spec 35: the v1 `.v-toggle` switch — the track + thumb (::after) live in CSS;
  // `data-on` drives the colour + thumb slide.
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className="v-toggle"
      data-on={checked ? "true" : "false"}
      data-slot="settings-switch"
    />
  );
}
