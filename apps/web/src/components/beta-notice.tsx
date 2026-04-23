"use client";

import { useT } from "@/lib/i18n/LocaleProvider";

/** User-facing honesty banner — not mock data. */
export function BetaNotice({ note }: { note?: string }) {
  const t = useT();
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3" data-testid="beta-notice">
      <div className="text-sm font-semibold text-amber-900">{t("beta.notice_title")}</div>
      <div className="text-xs text-amber-800">{note ?? t("beta.notice_default")}</div>
    </div>
  );
}
