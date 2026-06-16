import { ApiError } from "@/components/api-error";
import { PageTitleI18n } from "@/components/page-title-i18n";
import { apiGet } from "@/lib/api";
import type { Agent, ListResponse, LocalBridgeAgentState } from "@/lib/octopus-types";

import {
  ConnectionsClient,
  type ConnectionsAccount,
  type ConnectionsCallbackAudit,
  type ConnectionsCredential,
} from "./connections-client";

type LocalBridgeResponse = {
  data: {
    registered_agents: LocalBridgeAgentState[];
    reachable?: boolean;
    recent_callback_audit?: ConnectionsCallbackAudit[];
    bridge_runtime?: {
      handoff_dir?: string | null;
    };
  };
};

type MetricsResponse = {
  fault_recovery?: { waiting_handoffs?: number };
};

export default async function ConnectionsPage() {
  try {
    const [credResp, accResp, agentsResp, bridgeResp, metricsResp] = await Promise.all([
      apiGet<ListResponse<ConnectionsCredential>>("/credentials"),
      apiGet<ListResponse<ConnectionsAccount>>("/accounts").catch(() => ({
        items: [] as ConnectionsAccount[],
      })),
      apiGet<ListResponse<Agent>>("/agents"),
      apiGet<LocalBridgeResponse>("/local-bridge").catch(
        (): LocalBridgeResponse => ({
          data: { registered_agents: [] as LocalBridgeAgentState[] },
        })
      ),
      apiGet<MetricsResponse>("/metrics").catch((): MetricsResponse => ({})),
    ]);

    const bridgeData = bridgeResp.data ?? { registered_agents: [] };

    return (
      <div className="space-y-6 p-6">
        <PageTitleI18n
          titleKey="connections.title"
          subtitleKey="connections.subtitle"
        />
        <ConnectionsClient
          credentials={credResp.items}
          accounts={accResp.items}
          agents={agentsResp.items}
          bridgeAgents={bridgeData.registered_agents ?? []}
          bridgeReachable={!!bridgeData.reachable}
          handoffDir={bridgeData.bridge_runtime?.handoff_dir}
          waitingHandoffs={metricsResp.fault_recovery?.waiting_handoffs ?? 0}
          recentCallbacks={bridgeData.recent_callback_audit ?? []}
        />
      </div>
    );
  } catch (error) {
    return (
      <div className="space-y-6 p-6">
        <PageTitleI18n titleKey="connections.title" subtitleKey="connections.subtitle" />
        <ApiError error={error} />
      </div>
    );
  }
}
