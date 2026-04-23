"use client";

import { ApiError } from "@/components/api-error";
import { useT } from "@/lib/i18n/LocaleProvider";

export function AgentDetailLoadError({ error }: { error: unknown }) {
  const t = useT();
  return (
    <div className="space-y-6 p-6">
      <div className="space-y-1">
        <div className="text-xl font-semibold tracking-tight">{t("nav.agents")}</div>
        <div className="text-sm text-zinc-600">{t("agent_detail.load_failed")}</div>
      </div>
      <ApiError error={error} />
    </div>
  );
}
