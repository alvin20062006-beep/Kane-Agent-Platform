"use client";

import { useT } from "@/lib/i18n/LocaleProvider";

/**
 * 客户端版本的 PageTitle：接收 i18n key，自动翻译。
 * 用在 Server Component 的 page.tsx 里，避免整页改成 client。
 */
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
    <div className="space-y-1">
      <h1 className="text-xl font-semibold tracking-tight">
        {t(titleKey, titleFallback)}
      </h1>
      {subtitleKey ? (
        <p className="text-sm text-zinc-600">{t(subtitleKey, subtitleFallback)}</p>
      ) : null}
    </div>
  );
}
