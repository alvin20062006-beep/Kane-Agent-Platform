"use client";

import { useT } from "@/lib/i18n/LocaleProvider";

export function ApiError({ error }: { error: unknown }) {
  const t = useT();
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3">
      <div className="text-sm font-semibold text-rose-900">{t("apierror.title")}</div>
      <div className="text-xs text-rose-800 break-words">{msg}</div>
      <div className="mt-2 text-xs text-rose-800">
        {t("apierror.hint_prefix")}
        <code className="rounded bg-rose-100/80 px-1">apps/api</code>
        {t("apierror.hint_suffix_1")}
        <code className="rounded bg-rose-100/80 px-1">apps/web</code>
        {t("apierror.hint_suffix_2")}
        <code className="rounded bg-rose-100/80 px-1">NEXT_PUBLIC_API_BASE_URL</code>
        {t("apierror.hint_suffix_3")}
      </div>
    </div>
  );
}
