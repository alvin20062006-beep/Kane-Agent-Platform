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
  let details: AgentDetailResponse[];
  try {
    const agents = await apiGet<ListResponse<Agent>>("/agents");
    details = await Promise.all(
      agents.items.map((agent) =>
        apiGet<AgentDetailResponse>(`/agents/${encodeURIComponent(agent.agent_id)}`)
      )
    );
  } catch (error) {
    return (
      <div className="mx-auto max-w-[1500px] space-y-[var(--kane-section-gap)] px-[var(--kane-page-pad-x)] py-[var(--kane-page-pad-y)]">
        <FleetHeader />
        <ApiError error={error} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1500px] space-y-[var(--kane-section-gap)] px-[var(--kane-page-pad-x)] py-[var(--kane-page-pad-y)]">
      <FleetHeader />
      <AgentFleetClusterView details={details} />
    </div>
  );
}
