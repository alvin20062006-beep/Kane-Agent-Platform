"use client";

import { PageTitle } from "@/components/page-title";
import { useT } from "@/lib/i18n/LocaleProvider";

export function AgentDetailHeader({ displayName }: { displayName: string }) {
  const t = useT();
  return (
    <PageTitle
      title={t("agent_detail.title", displayName)}
      subtitle={t("agent_detail.subtitle")}
    />
  );
}

