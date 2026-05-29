import { currentUser } from "@clerk/nextjs/server";
import { getTranslations } from "next-intl/server";
import { PreferencesCard } from "@/components/settings/preferences-card";
import { Card } from "@/components/ui/card";
import { unwrap } from "@/lib/api";
import { serverApi } from "@/lib/api/server";

export default async function SettingsPage() {
  const t = await getTranslations("settings");
  const api = await serverApi();
  const [user, credits, usage] = await Promise.all([
    currentUser(),
    unwrap(await api.GET("/v1/me/credits")),
    unwrap(await api.GET("/v1/me/usage")),
  ]);

  const email = user?.primaryEmailAddress?.emailAddress ?? "";
  const name =
    [user?.firstName, user?.lastName].filter(Boolean).join(" ") || email;

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6">
      <h1 className="mb-6 font-heading text-3xl font-semibold tracking-tight">
        {t("title")}
      </h1>

      <div className="flex flex-col gap-5">
        {/* Account */}
        <Card className="gap-2 p-5">
          <h2 className="font-heading text-sm font-semibold tracking-wide text-muted-foreground uppercase">
            {t("account")}
          </h2>
          <p className="text-sm font-medium">{name}</p>
          {email && name !== email ? (
            <p className="text-sm text-muted-foreground">{email}</p>
          ) : null}
          <p className="text-xs text-muted-foreground">{t("accountHint")}</p>
        </Card>

        {/* Credits */}
        <Card className="gap-2 p-5">
          <h2 className="font-heading text-sm font-semibold tracking-wide text-muted-foreground uppercase">
            {t("credits")}
          </h2>
          <p className="font-heading text-3xl font-semibold tabular-nums">
            {credits.balance.toLocaleString()}
          </p>
          <p className="text-xs text-muted-foreground">{t("creditsHint")}</p>
        </Card>

        {/* Preferences */}
        <PreferencesCard />

        {/* Usage */}
        <Card className="gap-3 p-5">
          <h2 className="font-heading text-sm font-semibold tracking-wide text-muted-foreground uppercase">
            {t("usage")}
          </h2>
          {usage.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("usageEmpty")}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs text-muted-foreground uppercase">
                    <th className="py-2 pr-3 font-medium">{t("colWhen")}</th>
                    <th className="py-2 pr-3 font-medium">{t("colTier")}</th>
                    <th className="py-2 pr-3 font-medium">{t("colModel")}</th>
                    <th className="py-2 pr-3 text-right font-medium">
                      {t("colTokens")}
                    </th>
                    <th className="py-2 text-right font-medium">
                      {t("colCost")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {usage.map((row, i) => (
                    <tr
                      // biome-ignore lint/suspicious/noArrayIndexKey: usage rows have no id
                      key={i}
                      className="border-b last:border-0"
                    >
                      <td className="py-2 pr-3 whitespace-nowrap text-muted-foreground">
                        {new Date(row.created_at).toLocaleString()}
                      </td>
                      <td className="py-2 pr-3">
                        <span className="font-mono text-xs uppercase">
                          {row.tier_used}
                        </span>
                      </td>
                      <td className="py-2 pr-3 font-mono text-xs">
                        {row.model_name}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums">
                        {(
                          row.prompt_tokens + row.completion_tokens
                        ).toLocaleString()}
                      </td>
                      <td className="py-2 text-right tabular-nums">
                        ${(row.cost_cents / 100).toFixed(4)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
