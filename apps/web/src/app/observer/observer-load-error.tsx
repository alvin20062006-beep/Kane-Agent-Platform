"use client";

import { ApiError } from "@/components/api-error";
import { PageTitle } from "@/components/page-title";
import { useT } from "@/lib/i18n/LocaleProvider";

export function ObserverLoadError({ error }: { error: unknown }) {
  const t = useT();
  return (
    <div className="space-y-6 p-6">
      <PageTitle title={t("nav.observer")} subtitle={t("observer.load_error_subtitle")} />
      <ApiError error={error} />
    </div>
  );
}
