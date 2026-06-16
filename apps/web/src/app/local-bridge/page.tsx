import { ApiError } from "@/components/api-error";
import { apiGet } from "@/lib/api";
import type { LocalBridgeAgentState } from "@/lib/octopus-types";

import { LocalBridgeClient } from "./local-bridge-client";

type BridgeCallbackAuditItem = {
  kind: "accepted" | "rejected" | "duplicate" | "late";
  created_at: string;
  task_id?: string | null;
  run_id?: string | null;
  agent_id?: string | null;
  integration_path?: string | null;
  status?: string | null;
  message?: string | null;
  source?: string | null;
  correlation_id?: string | null;
};

type LocalBridgeResponse = {
  version?: string;
  data: {
    url: string;
    reachable: boolean | null;
    registered_agents: LocalBridgeAgentState[];
    last_seen_at?: string | null;
    metrics_bridge_registered_total?: number;
    recent_callback_audit?: BridgeCallbackAuditItem[];
    docs: string;
    bridge_runtime?: {
      reachable?: boolean | null;
      last_execute_at?: string | null;
      last_execute_error?: string | null;
      handoff_dir?: string | null;
      api_public_url?: string | null;
      probed_at?: string | null;
    };
  };
};

export default async function LocalBridgePage({
  searchParams,
}: {
  searchParams: Promise<{ taskId?: string; connect?: string }>;
}) {
  const { taskId, connect } = await searchParams;
  let response: LocalBridgeResponse;
  try {
    response = await apiGet<LocalBridgeResponse>("/local-bridge");
  } catch (error) {
    return (
      <div className="space-y-6 p-6">
        <div className="space-y-1">
          <div className="text-xl font-semibold tracking-tight">Local Bridge</div>
          <div className="text-sm text-zinc-600">Bridge registry and status</div>
        </div>
        <ApiError error={error} />
      </div>
    );
  }

  return (
    <LocalBridgeClient
      data={response.data}
      highlightTaskId={taskId ?? null}
      openConnectWizard={connect === "1"}
    />
  );
}
