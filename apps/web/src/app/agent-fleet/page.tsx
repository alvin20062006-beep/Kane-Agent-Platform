import { ApiError } from "@/components/api-error";
import { apiGet } from "@/lib/api";
import type { Agent, ListResponse, LocalBridgeAgentState } from "@/lib/octopus-types";

import { AgentFleetClusterView } from "./agent-fleet-cluster-view";
import { FleetHeader } from "./fleet-header";

type AgentDetailResponse = {
  data: Agent;
  bridge_state?: LocalBridgeAgentState | null;
};

export default async function AgentFleetPage() {
  try {
    const agents = await apiGet<ListResponse<Agent>>("/agents");
    const details = await Promise.all(
      agents.items.map((agent) =>
        apiGet<AgentDetailResponse>(`/agents/${encodeURIComponent(agent.agent_id)}`)
      )
    );

    return (
      <div className="space-y-6 p-6">
        <FleetHeader />
        <AgentFleetClusterView details={details} />
      </div>
    );
  } catch (error) {
    return (
      <div className="space-y-6 p-6">
        <FleetHeader />
        <ApiError error={error} />
      </div>
    );
  }
}
