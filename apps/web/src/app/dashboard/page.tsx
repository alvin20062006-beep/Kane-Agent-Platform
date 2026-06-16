import { ApiError } from "@/components/api-error";
import { apiGet } from "@/lib/api";
import type { AdvisorSuggestion, GovernorSummary, ObserverSummary, WatchdogStatus } from "@/lib/octopus-types";

import { DashboardClient } from "./dashboard-client";

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

export default async function DashboardPage() {
  let watchdog: { data: WatchdogStatus };
  let metrics: MetricsResponse;
  let observer: { data: ObserverSummary };
  let advisor: {
    data: {
      generated_at: string;
      totals: Record<string, number>;
      top_suggestions: AdvisorSuggestion[];
      pattern_summary: Array<{ pattern_key: string; occurrence_count: number; last_seen_at: string | null; affected_targets: number; confidence: string }>;
      policy_suggestion_summary: Array<{ suggestion_id: string; title: string; status: string; severity: string; confidence: string | null; occurrence_count: number; target_id: string; target_label: string | null; current_effective_mode: string | null; suggested_mode: string | null; matched_policy_id: string | null; policy_source: string | null }>;
    };
  };
  let governor: { data: GovernorSummary };
  let orchestratorMasters: { items: MasterBatchItem[] };
  try {
    [watchdog, metrics, observer, advisor, governor, orchestratorMasters] = await Promise.all([
      apiGet<{ data: WatchdogStatus }>("/watchdog"),
      apiGet<MetricsResponse>("/metrics"),
      apiGet<{ data: ObserverSummary }>("/observer"),
      apiGet<{
        data: {
          generated_at: string;
          totals: Record<string, number>;
          top_suggestions: AdvisorSuggestion[];
          pattern_summary: Array<{ pattern_key: string; occurrence_count: number; last_seen_at: string | null; affected_targets: number; confidence: string }>;
          policy_suggestion_summary: Array<{ suggestion_id: string; title: string; status: string; severity: string; confidence: string | null; occurrence_count: number; target_id: string; target_label: string | null; current_effective_mode: string | null; suggested_mode: string | null; matched_policy_id: string | null; policy_source: string | null }>;
        };
      }>("/advisor"),
      apiGet<{ data: GovernorSummary }>("/governor"),
      apiGet<{ items: MasterBatchItem[] }>("/api/kanaloa/orchestrator/tasks?limit=20").catch(() => ({
        items: [] as MasterBatchItem[],
      })),
    ]);
  } catch (error) {
    return (
      <div className="space-y-6 p-6">
        <div className="space-y-1">
          <div className="text-xl font-semibold tracking-tight">Dashboard</div>
          <div className="text-sm text-zinc-600">Unable to load dashboard metrics.</div>
        </div>
        <ApiError error={error} />
      </div>
    );
  }

  return (
    <DashboardClient
      watchdog={{ recovery_hints: watchdog.data.recovery_hints ?? [] }}
      metrics={metrics}
      observer={observer.data}
      advisor={advisor.data}
      governor={governor.data}
      masterBatches={orchestratorMasters.items ?? []}
    />
  );
}
