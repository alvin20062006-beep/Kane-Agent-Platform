"use client";

import { BetaNotice } from "@/components/beta-notice";
import { PageTitle } from "@/components/page-title";
import { useT } from "@/lib/i18n/LocaleProvider";
import type { WatchdogStatus } from "@/lib/octopus-types";

export function WatchdogClient({ data }: { data: WatchdogStatus }) {
  const t = useT();
  const { summary, events, recovery_hints: recoveryHints } = data;

  const summaryCards: Array<[string, string | number]> = [
    [t("watchdog.running_tasks"), summary.running_tasks],
    [t("watchdog.stalled_tasks"), summary.stalled_tasks],
    [t("watchdog.failed_runs_24h"), summary.failed_tasks_recent],
    [t("watchdog.waiting_handoffs"), summary.waiting_handoffs],
    [t("watchdog.offline_agents"), summary.offline_agents],
    [t("watchdog.degraded_agents"), summary.degraded_agents],
    [t("watchdog.bridge_reachable"), String(summary.bridge_reachable)],
    [t("watchdog.last_run"), summary.last_run_finished_at ?? t("dashboard.none")],
  ];

  return (
    <div className="space-y-6 p-6">
      <PageTitle title={t("watchdog.title")} subtitle={t("watchdog.subtitle")} />

      <BetaNotice note={t("watchdog.beta_notice")} />

      <section className="grid gap-4 md:grid-cols-3 xl:grid-cols-4">
        {summaryCards.map(([label, value]) => (
          <div
            key={label}
            className="rounded-lg border border-zinc-200 bg-white p-4"
          >
            <div className="text-xs text-zinc-600">{label}</div>
            <div className="mt-2 text-sm font-semibold">{value}</div>
          </div>
        ))}
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <div
          data-testid="watchdog-events-card"
          className="rounded-lg border border-zinc-200 bg-white p-4"
        >
          <div className="text-sm font-semibold">{t("watchdog.events")}</div>
          <div className="mt-3 space-y-3">
            {events.map((event) => (
              <div key={event.event_id} className="rounded-md border border-zinc-200 p-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="font-medium">
                    {event.type} • {event.severity}
                  </div>
                  <div className="text-xs text-zinc-500">{event.created_at}</div>
                </div>
                {event.message ? (
                  <div className="mt-2 text-sm text-zinc-700">{event.message}</div>
                ) : null}
                {event.recovery_hint ? (
                  <div className="mt-2 text-xs text-zinc-500">
                    {t("watchdog.recovery")}: {event.recovery_hint}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>

        <div
          data-testid="watchdog-recovery-hints"
          className="rounded-lg border border-zinc-200 bg-white p-4"
        >
          <div className="text-sm font-semibold">{t("watchdog.recovery_hints")}</div>
          <div className="mt-3 space-y-2">
            {recoveryHints.map((hint) => (
              <div key={hint} className="rounded-md border border-zinc-200 px-3 py-2 text-sm">
                {hint}
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

