import { ApiError } from "@/components/api-error";
import { apiGet } from "@/lib/api";
import type { LocalBridgeAgentState } from "@/lib/octopus-types";

import { LocalBridgeClient } from "./local-bridge-client";

type LocalBridgeResponse = {
  beta: boolean;
  data: {
    url: string;
    reachable: boolean | null;
    registered_agents: LocalBridgeAgentState[];
    last_seen_at?: string | null;
    metrics_bridge_registered_total?: number;
    docs: string;
  };
};

export default async function LocalBridgePage() {
  try {
    const response = await apiGet<LocalBridgeResponse>("/local-bridge");

    return <LocalBridgeClient data={response.data} />;
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
}
