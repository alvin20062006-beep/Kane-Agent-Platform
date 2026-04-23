import { apiGet } from "@/lib/api";
import type { Agent, LocalBridgeAgentState } from "@/lib/octopus-types";

import { AgentConfigClient } from "./agent-config-client";
import { AgentDetailHeader } from "./agent-detail-header";
import { AgentDetailLoadError } from "./agent-detail-load-error";

type Resp = {
  data: Agent;
  bridge_state?: LocalBridgeAgentState | null;
  api_profile?: unknown;
};

export default async function AgentFleetDetailPage({
  params,
}: {
  params: Promise<{ agentId: string }>;
}) {
  const { agentId } = await params;
  try {
    const initial = await apiGet<Resp>(`/agents/${encodeURIComponent(agentId)}`);
    return (
      <div className="space-y-6 p-6">
        <AgentDetailHeader displayName={initial.data.display_name} />
        <AgentConfigClient agentId={agentId} initial={initial} />
      </div>
    );
  } catch (error) {
    return <AgentDetailLoadError error={error} />;
  }
}
