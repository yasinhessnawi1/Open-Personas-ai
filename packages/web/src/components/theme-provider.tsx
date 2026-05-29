"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ComponentProps } from "react";

// Dark mode (D-09-10): class-based (globals.css `@custom-variant dark`), system
// default, toggle persisted by next-themes to localStorage. Wraps the app once
// in the root layout.
export function ThemeProvider({
  children,
  ...props
}: ComponentProps<typeof NextThemesProvider>) {
  return <NextThemesProvider {...props}>{children}</NextThemesProvider>;
}
