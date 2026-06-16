"use client";

import { useT } from "@/lib/i18n/LocaleProvider";

export function PartialSettingsError({ apiBase }: { apiBase: string }) {
  const t = useT();
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
      <div className="font-semibold">{t("settings.partial.title")}</div>
      <p className="mt-2 text-xs leading-relaxed">
        {t("settings.partial.hint_prefix")}
        <code className="rounded bg-white/60 px-1">apps/api</code>
        {t("settings.partial.hint_mid")}
        <code className="rounded bg-white/60 px-1">NEXT_PUBLIC_API_BASE_URL</code>
        {t("settings.partial.hint_suffix")}
        <span className="ml-1 font-mono text-xs">{apiBase}</span>
      </p>
    </div>
  );
}
