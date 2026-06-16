"use client";

import Link from "next/link";

import { ProductNotice } from "@/components/product-notice";
import { PageTitle } from "@/components/page-title";
import { useT } from "@/lib/i18n/LocaleProvider";
import { masterIsActive, subtaskProgress } from "@/lib/task-completion";
import type { AdvisorSuggestion, GovernorSummary, ObserverSummary } from "@/lib/octopus-types";

type MasterBatchItem = {
  master_task_id: string;
  user_instruction: string;
  status: string;
  subtasks?: Array<{ status?: string }>;
};

type MetricsResponse = {
  version?: string;
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
    open_issues?: number;
    escalated_issues?: number;
    resolved_issues?: number;
  };
  worker?: {
    running: boolean;
    started_at?: string;
    last_tick_at?: string | null;
    queued_runs?: number;
    queued_by_priority?: Record<string, number>;
    scheduler?: {
      max_concurrent_runs: number;
      per_agent_serialization: boolean;
      poll_interval_seconds: number;
    };
  };
  notifications?: { deliveries_total?: number; deliveries_failed_recent?: number };
  orchestrator?: { active_masters?: number };
};

type WatchdogStatus = { recovery_hints: string[] };

type PatternSummaryItem = {
  pattern_key: string;
  occurrence_count: number;
  last_seen_at: string | null;
  affected_targets: number;
  confidence: string;
};

type PolicySuggestionItem = {
  suggestion_id: string;
  title: string;
  status: string;
  confidence: string | null;
  occurrence_count: number;
  target_label: string | null;
  current_effective_mode: string | null;
  suggested_mode: string | null;
  policy_source: string | null;
};

export function DashboardClient({
  watchdog,
  metrics,
  observer,
  advisor,
  governor,
  masterBatches = [],
}: {
  watchdog: WatchdogStatus;
  metrics: MetricsResponse;
  observer: ObserverSummary;
  governor?: GovernorSummary;
  advisor: {
    generated_at: string;
    totals: Record<string, number>;
    top_suggestions: AdvisorSuggestion[];
    pattern_summary?: PatternSummaryItem[];
    policy_suggestion_summary?: PolicySuggestionItem[];
  };
  masterBatches?: MasterBatchItem[];
}) {
  const t = useT();

  const openIssues = (metrics.fault_recovery.open_issues ?? 0) + (metrics.fault_recovery.escalated_issues ?? 0);
  const waitingHandoffs = metrics.fault_recovery.waiting_handoffs ?? 0;
  const activeOrchestrators = metrics.orchestrator?.active_masters ?? 0;
  const activeBatches = masterBatches.filter((m) => masterIsActive(m.status));

  const metricCards: Array<[string, string, string]> = [
    ["conversations", t("dashboard.metric.conversations"), String(metrics.conversations.total)],
    ["tasks", t("dashboard.metric.tasks"), String(metrics.tasks.total)],
    ["runs", t("dashboard.metric.runs"), String(metrics.runs.total)],
    ["bridge_agents", t("dashboard.metric.bridge_agents"), String(metrics.local_bridge.registered_agents)],
  ];

  const quickLinks: Array<[string, string]> = [
    [t("topbar.watchdog"), "/watchdog"],
    ["Observer", "/observer"],
  ];

  return (
    <div className="space-y-6 p-6">
      <PageTitle title={t("dashboard.title")} subtitle={t("dashboard.subtitle")} />

      <ProductNotice note={t("dashboard.notice")} />

      {openIssues > 0 || waitingHandoffs > 0 || activeOrchestrators > 0 ? (
        <div className="space-y-2">
          {openIssues > 0 ? (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900">
              <span>{t("dashboard.alert_issues").replace("{n}", String(openIssues))}</span>
              <Link href="/watchdog" className="text-xs font-medium underline">
                {t("task_detail.open_watchdog")}
              </Link>
            </div>
          ) : null}
          {waitingHandoffs > 0 ? (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-sky-200 bg-sky-50 px-4 py-2 text-sm text-sky-900">
              <span>{t("dashboard.alert_handoffs").replace("{n}", String(waitingHandoffs))}</span>
              <Link href="/local-bridge" className="text-xs font-medium underline">
                {t("task_detail.open_bridge")}
              </Link>
            </div>
          ) : null}
          {activeOrchestrators > 0 ? (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-violet-200 bg-violet-50 px-4 py-2 text-sm text-violet-900">
              <span>{t("dashboard.alert_orchestrator").replace("{n}", String(activeOrchestrators))}</span>
              <Link href="/orchestrator" className="text-xs font-medium underline">
                {t("nav.orchestrator")}
              </Link>
            </div>
          ) : null}
        </div>
      ) : null}

      {activeBatches.length > 0 ? (
        <section data-testid="dashboard-active-batches" className="rounded-lg border border-violet-200 bg-violet-50/50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm font-semibold text-violet-950">{t("dashboard.active_batches_title")}</div>
            <Link href="/orchestrator" className="text-xs text-violet-800 underline">
              {t("nav.orchestrator")}
            </Link>
          </div>
          <div className="mt-3 space-y-3">
            {activeBatches.slice(0, 5).map((batch) => {
              const prog = subtaskProgress(batch.subtasks ?? []);
              return (
                <div key={batch.master_task_id} className="rounded-md border border-violet-200 bg-white p-3 text-sm">
                  <div className="font-medium line-clamp-1">{batch.user_instruction}</div>
                  <div className="mt-1 text-xs text-violet-800 font-mono">{batch.master_task_id}</div>
                  <div className="mt-2 flex items-center gap-2">
                    <div className="h-1.5 flex-1 rounded-full bg-violet-100">
                      <div
                        className="h-1.5 rounded-full bg-violet-600"
                        style={{ width: `${prog.pct}%` }}
                      />
                    </div>
                    <span className="text-xs text-zinc-600">
                      {t("dashboard.batch_progress")
                        .replace("{done}", String(prog.done))
                        .replace("{total}", String(prog.total))}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

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
          <div className="mt-3 flex flex-wrap gap-2">
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
            <div>{t("dashboard.bridge_reachable")}: {String(metrics.local_bridge.reachable)}</div>
            <div>{t("dashboard.recent_failed_runs")}: {metrics.fault_recovery.recent_failed_runs}</div>
            <div>{t("dashboard.open_issues")}: {metrics.fault_recovery.open_issues ?? 0}</div>
            <div>{t("dashboard.escalated_issues")}: {metrics.fault_recovery.escalated_issues ?? 0}</div>
            <div>{t("dashboard.queued_runs")}: {metrics.runs.queued ?? 0}</div>
            <div>{t("dashboard.retry_supported")}: {String(metrics.fault_recovery.retry_supported)}</div>
            <div>{t("dashboard.last_bridge_heartbeat")}: {metrics.local_bridge.last_seen_at ?? t("dashboard.none")}</div>
            <div>{t("dashboard.last_run_activity")}: {metrics.runs.last_finished_or_started_at ?? t("dashboard.none")}</div>
            {metrics.worker ? (
              <div className="space-y-1">
                <div>
                  {t("dashboard.worker_running")}: {String(metrics.worker.running)} · {t("dashboard.last_tick")}:{" "}
                  {metrics.worker.last_tick_at ?? t("dashboard.none")}
                </div>
                <div>
                  scheduler: slots={metrics.worker.scheduler?.max_concurrent_runs ?? 1} / per-agent=
                  {String(metrics.worker.scheduler?.per_agent_serialization ?? true)}
                </div>
                <div>queued by priority: {JSON.stringify(metrics.worker.queued_by_priority ?? {})}</div>
              </div>
            ) : null}
            {metrics.notifications ? (
              <div>
                {t("dashboard.notifications")}: {metrics.notifications.deliveries_total ?? 0} ·{" "}
                {t("dashboard.failed_recent")}: {metrics.notifications.deliveries_failed_recent ?? 0}
              </div>
            ) : null}
          </div>
        </div>

        <div data-testid="dashboard-observer-card" className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-semibold">Observer</div>
            <Link href="/observer" className="text-xs text-zinc-600 underline">
              Open observer
            </Link>
          </div>
          <div className="mt-3 space-y-2 text-sm text-zinc-700">
            <div>Recent packets: {observer.recent_packets.length}</div>
            <div>Failure patterns: {observer.failure_patterns.length}</div>
            <div>Success patterns: {observer.success_patterns.length}</div>
            <div>Recovery patterns: {observer.recovery_patterns.length}</div>
            {observer.failure_patterns[0] ? (
              <div className="rounded-md border border-zinc-200 px-3 py-2 text-xs">
                top failure: {observer.failure_patterns[0].key} ({observer.failure_patterns[0].count})
              </div>
            ) : null}
          </div>
        </div>
      </section>

      <section data-testid="dashboard-advisor-card" className="rounded-lg border border-zinc-200 bg-white p-4">
        <div className="flex items-center justify-between gap-3">
          <div className="text-sm font-semibold">Top Advisor Suggestions</div>
          <div className="text-xs text-zinc-500">
            open={advisor.totals.open ?? 0} / total={advisor.totals.total ?? 0}
          </div>
        </div>
        <div className="mt-3 space-y-3">
          {advisor.top_suggestions.length ? (
            advisor.top_suggestions.map((suggestion) => (
              <div key={suggestion.suggestion_id} className="rounded-md border border-zinc-200 p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="font-medium">{suggestion.title}</div>
                  <div className="text-xs text-zinc-500">
                    {suggestion.severity} / {suggestion.status} / confidence={suggestion.confidence ?? "low"}
                  </div>
                </div>
                <div className="mt-2 text-zinc-700">{suggestion.summary}</div>
                <div className="mt-2 flex flex-wrap gap-2 text-xs text-zinc-500">
                  <span className="rounded-full border border-zinc-200 px-2 py-1">
                    occurrences={suggestion.occurrence_count ?? 1}
                  </span>
                  <span className="rounded-full border border-zinc-200 px-2 py-1">
                    affected_targets={suggestion.affected_targets ?? 1}
                  </span>
                </div>
                <div className="mt-2 text-xs text-zinc-500">
                  next: {suggestion.recommended_action}
                </div>
                {suggestion.next_action_hint ? (
                  <div className="mt-2 rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-700">
                    Action: {suggestion.next_action_hint}
                    {suggestion.next_action_url ? (
                      <Link href={suggestion.next_action_url} className="ml-2 underline">
                        Go →
                      </Link>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ))
          ) : (
            <div className="text-sm text-zinc-500">No advisor suggestions have been generated yet.</div>
          )}
        </div>
      </section>

      {(advisor.pattern_summary ?? []).length > 0 ? (
        <section data-testid="dashboard-advisor-patterns" className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-sm font-semibold">Repeated Failure Patterns</div>
          <div className="mt-3 space-y-2">
            {(advisor.pattern_summary ?? []).map((p) => (
              <div key={p.pattern_key} className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-zinc-200 px-3 py-2 text-sm">
                <div className="font-medium text-zinc-800">{p.pattern_key}</div>
                <div className="flex flex-wrap gap-2 text-xs text-zinc-500">
                  <span className="rounded-full border border-zinc-200 px-2 py-1">occurrences={p.occurrence_count}</span>
                  <span className="rounded-full border border-zinc-200 px-2 py-1">targets={p.affected_targets}</span>
                  <span className="rounded-full border border-zinc-200 px-2 py-1">confidence={p.confidence}</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {(advisor.policy_suggestion_summary ?? []).length > 0 ? (
        <section data-testid="dashboard-advisor-policy-suggestions" className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-sm font-semibold">Top Policy Suggestions</div>
          <div className="mt-3 space-y-2">
            {(advisor.policy_suggestion_summary ?? []).map((p) => (
              <div key={p.suggestion_id} className="rounded-md border border-zinc-200 px-3 py-2 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="font-medium">{p.title}</div>
                  <div className="text-xs text-zinc-500">
                    {p.status} / confidence={p.confidence ?? "low"} / occurrences={p.occurrence_count}
                  </div>
                </div>
                {p.current_effective_mode && p.suggested_mode ? (
                  <div className="mt-1 text-xs text-zinc-500">
                    {p.target_label ?? p.suggestion_id}: {p.current_effective_mode} → {p.suggested_mode}
                    {p.policy_source ? ` (${p.policy_source})` : null}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {governor ? (
        <section data-testid="dashboard-governor-card" className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-semibold">Governor</div>
            <div className="flex flex-wrap gap-2 text-xs">
              <span className={`rounded-full border px-2 py-0.5 ${governor.governor_enabled ? "border-green-200 bg-green-50 text-green-700" : "border-red-200 bg-red-50 text-red-700"}`}>
                {governor.governor_enabled ? "enabled" : "DISABLED"}
              </span>
              <span className={`rounded-full border px-2 py-0.5 ${governor.auto_execute_enabled ? "border-blue-200 bg-blue-50 text-blue-700" : "border-zinc-200 text-zinc-500"}`}>
                auto={governor.auto_execute_enabled ? "on" : "off"}
              </span>
            </div>
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center text-sm">
            <div className="rounded-md border border-zinc-100 p-2">
              <div className="text-lg font-semibold">{governor.totals.pending}</div>
              <div className="text-xs text-zinc-500">pending</div>
            </div>
            <div className="rounded-md border border-zinc-100 p-2">
              <div className="text-lg font-semibold">{governor.totals.executed}</div>
              <div className="text-xs text-zinc-500">executed</div>
            </div>
            <div className="rounded-md border border-zinc-100 p-2">
              <div className="text-lg font-semibold">{governor.totals.denied}</div>
              <div className="text-xs text-zinc-500">denied</div>
            </div>
          </div>
          {governor.totals.pending > 0 ? (
            <div className="mt-3">
              <Link href="/governor" className="text-xs text-blue-600 underline">
                {governor.totals.pending} decision(s) awaiting confirmation →
              </Link>
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
