"use client";

import { ApiError } from "@/components/api-error";
import { WorkPage } from "@/components/page-shell";
import { useT } from "@/lib/i18n/LocaleProvider";

export function ConversationsLoadError({ error }: { error: unknown }) {
  const t = useT();
  return (
    <WorkPage title={t("nav.conversations")} subtitle={t("conv.page.subtitle")}>
      <div className="p-6">
        <ApiError error={error} />
      </div>
    </WorkPage>
  );
}
