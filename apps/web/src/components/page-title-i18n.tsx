"use client";

import { useT } from "@/lib/i18n/LocaleProvider";

export function PageTitleI18n({
  titleKey,
  subtitleKey,
  titleFallback,
  subtitleFallback,
}: {
  titleKey: string;
  subtitleKey?: string;
  titleFallback?: string;
  subtitleFallback?: string;
}) {
  const t = useT();
  return (
    <div className="kane-page-header">
      <h1 className="kane-page-title">{t(titleKey, titleFallback)}</h1>
      {subtitleKey ? (
        <p className="kane-page-subtitle">{t(subtitleKey, subtitleFallback)}</p>
      ) : null}
    </div>
  );
}
