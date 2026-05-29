import { auth } from "@clerk/nextjs/server";
import { ArrowRight, FileText, Gauge, Workflow, Wrench } from "lucide-react";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { ThemeToggle } from "@/components/theme-toggle";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default async function Home() {
  const t = await getTranslations("landing");
  const tApp = await getTranslations("app");
  const { userId } = await auth();
  const signedIn = Boolean(userId);

  const features = [
    { icon: FileText, key: "identity" },
    { icon: Wrench, key: "tools" },
    { icon: Workflow, key: "runs" },
    { icon: Gauge, key: "routing" },
  ] as const;

  const primaryCta = signedIn ? (
    <Link
      href="/personas"
      className={cn(buttonVariants({ size: "lg" }), "gap-2")}
    >
      {t("openApp")}
      <ArrowRight className="size-4" />
    </Link>
  ) : (
    <Link
      href="/sign-up"
      className={cn(buttonVariants({ size: "lg" }), "gap-2")}
    >
      {t("getStarted")}
      <ArrowRight className="size-4" />
    </Link>
  );

  return (
    <div className="flex min-h-svh flex-col">
      {/* Top bar */}
      <header className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b bg-background/80 px-4 backdrop-blur sm:px-6">
        <span className="font-heading text-lg font-semibold tracking-tight">
          {tApp("name")}
        </span>
        <div className="flex-1" />
        <ThemeToggle />
        {signedIn ? (
          <Link href="/personas" className={cn(buttonVariants({ size: "sm" }))}>
            {t("openApp")}
          </Link>
        ) : (
          <>
            <Link
              href="/sign-in"
              className={cn(buttonVariants({ variant: "ghost", size: "sm" }))}
            >
              {t("signIn")}
            </Link>
            <Link
              href="/sign-up"
              className={cn(buttonVariants({ size: "sm" }))}
            >
              {t("getStarted")}
            </Link>
          </>
        )}
      </header>

      <main className="flex-1">
        {/* Hero */}
        <section className="relative overflow-hidden border-b">
          {/* Warm editorial glow — atmosphere, not a flat fill. */}
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 bg-gradient-to-b from-primary/6 via-transparent to-transparent"
          />
          <div className="relative mx-auto w-full max-w-4xl px-6 py-20 sm:py-28">
            <p className="font-mono text-xs tracking-widest text-primary uppercase">
              {t("kicker")}
            </p>
            <h1 className="mt-4 max-w-3xl text-balance font-heading text-4xl leading-[1.05] font-semibold tracking-tight sm:text-6xl">
              {t("headline")}
            </h1>
            <p className="mt-6 max-w-xl text-balance text-lg text-muted-foreground">
              {t("subhead")}
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-3">
              {primaryCta}
              {signedIn ? null : (
                <Link
                  href="/sign-in"
                  className={cn(
                    buttonVariants({ variant: "outline", size: "lg" }),
                  )}
                >
                  {t("signIn")}
                </Link>
              )}
            </div>

            {/* Tier escalation motif — the routing layer made tangible. */}
            <div className="mt-12 flex items-center gap-3">
              <span className="font-mono text-[0.65rem] tracking-wide text-muted-foreground uppercase">
                {t("tierRail")}
              </span>
              <div className="flex items-center gap-1.5">
                <TierDot className="bg-tier-small" label={t("tierSmall")} />
                <span className="h-px w-4 bg-border" />
                <TierDot className="bg-tier-mid" label={t("tierMid")} />
                <span className="h-px w-4 bg-border" />
                <TierDot
                  className="bg-tier-frontier"
                  label={t("tierFrontier")}
                />
              </div>
            </div>
          </div>
        </section>

        {/* Feature beats */}
        <section className="mx-auto w-full max-w-4xl px-6 py-16">
          <div className="grid gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-2">
            {features.map(({ icon: Icon, key }) => (
              <div key={key} className="flex flex-col gap-2 bg-card p-6">
                <Icon className="size-5 text-primary" />
                <h2 className="font-heading text-lg font-semibold tracking-tight">
                  {t(`features.${key}.title`)}
                </h2>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {t(`features.${key}.body`)}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* Closing CTA */}
        <section className="border-t">
          <div className="mx-auto flex w-full max-w-4xl flex-col items-start gap-4 px-6 py-16 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="max-w-md text-balance font-heading text-2xl font-semibold tracking-tight">
              {t("ctaTitle")}
            </h2>
            {primaryCta}
          </div>
        </section>
      </main>

      <footer className="border-t">
        <div className="mx-auto flex w-full max-w-4xl flex-col gap-1 px-6 py-8 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <span className="font-heading font-medium text-foreground">
            {tApp("name")}
          </span>
          <span>{t("footer")}</span>
        </div>
      </footer>
    </div>
  );
}

function TierDot({ className, label }: { className: string; label: string }) {
  return (
    <span
      role="img"
      title={label}
      className={cn("size-2.5 rounded-full", className)}
      aria-label={label}
    />
  );
}
