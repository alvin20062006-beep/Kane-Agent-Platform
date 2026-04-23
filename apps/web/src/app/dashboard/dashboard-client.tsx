"use client";

import Link from "next/link";

import { BetaNotice } from "@/components/beta-notice";
import { PageTitle } from "@/components/page-title";
import { useT } from "@/lib/i18n/LocaleProvider";

type MetricsResponse = {
  beta: boolean;
  tasks: { total: number; by_status: Record<string, number> };
  conversations: { total: number };
  runs: {
    total: number;
    succeeded: number;
    failed: number;
    queued?: number;
    last_finished_or_started_at?: string | null;
  };
  agents: { total: number; by_status: Record<string, number> };
  local_bridge: {
    reachable: boolean | null;
    url: string;
    registered_agents: number;
    last_seen_at?: string | null;
  };
  fault_recovery: {
    waiting_handoffs: number;
    recent_failed_runs: number;
    retry_supported: boolean;
  };
  worker?: {
    running: boolean;
    started_at?: string;
    last_tick_at?: string | null;
    queued_runs?: number;
  };
  notifications?: { deliveries_total?: number; deliveries_failed_recent?: number };
};

type WatchdogStatus = { recovery_hints: string[] };
type Task = { task_id: string; title: string; status: string; created_at: string; updated_at?: string | null };
type Run = {
  run_id: string;
  status: string;
  integration_path?: string | null;
  started_at?: string | null;
  error?: string | null;
};

export function DashboardClient({
  watchdog,
  metrics,
}: {
  watchdog: WatchdogStatus;
  metrics: MetricsResponse;
}) {
  const t = useT();

  const metricCards: Array<[string, string, string]> = [
    ["conversations", t("dashboard.metric.conversations"), String(metrics.conversations.total)],
    ["tasks", t("dashboard.metric.tasks"), String(metrics.tasks.total)],
    ["runs", t("dashboard.metric.runs"), String(metrics.runs.total)],
    ["bridge_agents", t("dashboard.metric.bridge_agents"), String(metrics.local_bridge.registered_agents)],
  ];

  const quickLinks: Array<[string, string]> = [[t("topbar.watchdog"), "/watchdog"]];

  return (
    <div className="space-y-6 p-6">
      <PageTitle title={t("dashboard.title")} subtitle={t("dashboard.subtitle")} />

      <BetaNotice note={t("dashboard.beta_notice")} />

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {metricCards.map(([id, label, value]) => (
          <div
            data-testid={`dashboard-metric-${id}`}
            key={id}
            className="rounded-lg border border-zinc-200 bg-white p-4"
          >
            <div className="text-xs text-zinc-600">{label}</div>
            <div className="mt-2 text-2xl font-semibold">{value}</div>
          </div>
        ))}
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.1fr_1.6fr_1.3fr]">
        <div data-testid="dashboard-watchdog-hints" className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-sm font-semibold">{t("dashboard.watchdog_hints")}</div>
          <div className="mt-3 space-y-2 text-sm text-zinc-700">
            {(watchdog.recovery_hints ?? []).length ? (
              watchdog.recovery_hints.map((hint) => (
                <div key={hint} className="rounded-md border border-zinc-200 px-3 py-2">
                  {hint}
                </div>
              ))
            ) : (
              <div className="text-sm text-zinc-500">{t("dashboard.no_hints")}</div>
            )}
          </div>
          <div className="mt-3">
            {quickLinks.map(([label, href]) => (
              <Link
                key={href}
                href={href}
                className="inline-flex items-center rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm hover:bg-zinc-50"
              >
                {label}
              </Link>
            ))}
          </div>
        </div>

        <div
          data-testid="dashboard-recovery-posture"
          className="rounded-lg border border-zinc-200 bg-white p-4"
        >
          <div className="text-sm font-semibold">{t("dashboard.recovery_posture")}</div>
          <div className="mt-3 space-y-2 text-sm text-zinc-700">
            <div>
              {t("dashboard.bridge_reachable")}: {String(metrics.local_bridge.reachable)}
            </div>
            <div>
              {t("dashboard.recent_failed_runs")}: {metrics.fault_recovery.recent_failed_runs}
            </div>
            <div>
              {t("dashboard.queued_runs")}: {metrics.runs.queued ?? 0}
            </div>
            <div>
              {t("dashboard.retry_supported")}: {String(metrics.fault_recovery.retry_supported)}
            </div>
            <div>
              {t("dashboard.last_bridge_heartbeat")}: {metrics.local_bridge.last_seen_at ?? t("dashboard.none")}
            </div>
            <div>
              {t("dashboard.last_run_activity")}: {metrics.runs.last_finished_or_started_at ?? t("dashboard.none")}
            </div>
            {metrics.worker ? (
              <div>
                {t("dashboard.worker_running")}: {String(metrics.worker.running)} • {t("dashboard.last_tick")}:{" "}
                {metrics.worker.last_tick_at ?? t("dashboard.none")}
              </div>
            ) : null}
            {metrics.notifications ? (
              <div>
                {t("dashboard.notifications")}: {metrics.notifications.deliveries_total ?? 0} •{" "}
                {t("dashboard.failed_recent")}: {metrics.notifications.deliveries_failed_recent ?? 0}
              </div>
            ) : null}
          </div>
        </div>

        <div />
      </section>
    </div>
  );
}

