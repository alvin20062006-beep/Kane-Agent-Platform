import Link from "next/link";

import { ApiError } from "@/components/api-error";
import { apiGet } from "@/lib/api";
import type { WatchdogStatus } from "@/lib/octopus-types";

import { DashboardClient } from "./dashboard-client";

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
  worker?: { running: boolean; started_at?: string; last_tick_at?: string | null; queued_runs?: number };
  notifications?: { deliveries_total?: number; deliveries_failed_recent?: number };
};

export default async function DashboardPage() {
  try {
    const [watchdog, metrics] = await Promise.all([
      apiGet<{ data: WatchdogStatus }>("/watchdog"),
      apiGet<MetricsResponse>("/metrics"),
    ]);

    return (
      <DashboardClient
        watchdog={{ recovery_hints: watchdog.data.recovery_hints ?? [] }}
        metrics={metrics}
      />
    );
  } catch (error) {
    return (
      <div className="space-y-6 p-6">
        <div className="space-y-1">
          <div className="text-xl font-semibold tracking-tight">Dashboard</div>
          <div className="text-sm text-zinc-600">Real beta system health</div>
        </div>
        <ApiError error={error} />
      </div>
    );
  }
}
