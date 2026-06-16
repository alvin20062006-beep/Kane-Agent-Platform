"use client";

import { useT } from "@/lib/i18n/LocaleProvider";

/** Context banner for deployment / integration notes (not mock data). */
export function ProductNotice({ note }: { note?: string }) {
  const t = useT();
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3" data-testid="product-notice">
      <div className="text-sm font-semibold text-amber-900">{t("notice.title")}</div>
      <div className="text-xs text-amber-800">{note ?? t("notice.default")}</div>
    </div>
  );
}
