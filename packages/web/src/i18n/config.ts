// Client-safe i18n constants (no server-only imports), so both the server
// request config and client components (the Settings language switcher) can use
// them. The pseudo-locale "xx" exercises acceptance #9.
export const DEFAULT_LOCALE = "en";
export const LOCALES = ["en", "xx"] as const;
export const LOCALE_COOKIE = "NEXT_LOCALE";
