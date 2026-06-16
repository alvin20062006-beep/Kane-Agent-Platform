"use client";

import { ProductNotice } from "@/components/product-notice";
import { PageTitle } from "@/components/page-title";
import { useT } from "@/lib/i18n/LocaleProvider";
import type { ObserverSummary } from "@/lib/octopus-types";

function totalLabel(key: string, t: (k: string) => string): string {
  const k = `observer.totals.${key}`;
  const resolved = t(k);
  return resolved === k ? key : resolved;
}

export function ObserverClient({ data }: { data: ObserverSummary }) {
  const t = useT();
  const sections: Array<{
    titleKey: string;
    items: Array<{ key: string; count: number; latest_at?: string | null; summary?: string | null }>;
  }> = [
    { titleKey: "observer.section_failure", items: data.failure_patterns },
    { titleKey: "observer.section_success", items: data.success_patterns },
    { titleKey: "observer.section_recovery", items: data.recovery_patterns },
  ];

  return (
    <div className="space-y-6 p-6">
      <PageTitle title={t("nav.observer")} subtitle={t("observer.subtitle")} />
      <ProductNotice note={t("observer.notice")} />

      <div className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs text-zinc-700">{t("observer.hint_time_basis")}</div>

      <section className="grid gap-4 md:grid-cols-5">
        {Object.entries(data.totals).map(([key, value]) => (
          <div key={key} className="rounded-lg border border-zinc-200 bg-white p-4">
            <div className="text-xs text-zinc-500">{totalLabel(key, t)}</div>
            <div className="mt-2 text-2xl font-semibold tabular-nums">{value}</div>
          </div>
        ))}
      </section>

      <section className="rounded-lg border border-zinc-200 bg-white p-4">
        <div className="text-sm font-semibold text-zinc-800">{t("observer.section_recent_packets")}</div>
        <div className="mt-3 space-y-3">
          {data.recent_packets.length ? (
            data.recent_packets.map((packet) => (
              <div key={packet.packet_id} className="rounded-md border border-zinc-200 p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="font-medium font-mono text-xs">
                    {packet.task_id} / {packet.run_id ?? t("observer.task_only")}
                  </div>
                  <div className="text-right text-xs text-zinc-500">
                    <div>{packet.created_at}</div>
                    <div>
                      {t("observer.lbl_time_basis")}: {packet.time_basis ?? "—"}
                    </div>
                  </div>
                </div>
                <div className="mt-2 grid gap-2 md:grid-cols-3 text-xs text-zinc-600">
                  <div>
                    {t("observer.lbl_status")}: {packet.status}
                  </div>
                  <div>
                    {t("observer.lbl_mode")}: {packet.execution_mode ?? "—"}
                  </div>
                  <div>
                    {t("observer.lbl_priority")}: {packet.queue_priority ?? "—"}
                  </div>
                  <div>
                    {t("observer.lbl_agent")}: {packet.agent_id ?? "—"}
                  </div>
                  <div>
                    {t("observer.lbl_path")}: {packet.integration_path ?? "—"}
                  </div>
                  <div>
                    {t("observer.lbl_recovery")}: {packet.recovery_state ?? "—"}
                  </div>
                </div>
                {packet.issue_class || packet.error ? (
                  <div className="mt-2 text-sm text-rose-700">
                    {packet.issue_class ?? packet.error}: {packet.error ?? packet.summary}
                  </div>
                ) : null}
                {packet.summary ? <div className="mt-2 text-sm text-zinc-700">{packet.summary}</div> : null}
              </div>
            ))
          ) : (
            <div className="text-sm text-zinc-500">{t("observer.empty_packets")}</div>
          )}
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-3">
        {sections.map((section) => (
          <div key={section.titleKey} className="rounded-lg border border-zinc-200 bg-white p-4">
            <div className="text-sm font-semibold text-zinc-800">{t(section.titleKey)}</div>
            <div className="mt-3 space-y-2">
              {section.items.length ? (
                section.items.map((item) => (
                  <div key={item.key} className="rounded-md border border-zinc-200 p-3 text-sm">
                    <div className="font-medium break-all">{item.key}</div>
                    <div className="mt-1 text-xs text-zinc-500">
                      {t("observer.pattern_count")}: {item.count} · {t("observer.pattern_latest")}:{" "}
                      {item.latest_at ?? "—"}
                    </div>
                    {item.summary ? <div className="mt-2 text-zinc-700">{item.summary}</div> : null}
                  </div>
                ))
              ) : (
                <div className="text-sm text-zinc-500">{t("observer.no_patterns")}</div>
              )}
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}
