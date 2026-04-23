"use client";

import { useT } from "@/lib/i18n/LocaleProvider";

export function SettingsSuspenseFallback() {
  const t = useT();
  return <div className="p-6 text-sm text-zinc-400">{t("common.loading")}</div>;
}
