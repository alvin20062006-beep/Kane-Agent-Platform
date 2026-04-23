import { ApiError } from "@/components/api-error";
import { PageTitleI18n } from "@/components/page-title-i18n";
import { apiGet } from "@/lib/api";
import type { Agent, ListResponse, LocalBridgeAgentState } from "@/lib/octopus-types";

import {
  ConnectionsClient,
  type ConnectionsAccount,
  type ConnectionsCredential,
} from "./connections-client";

type LocalBridgeResponse = {
  data: {
    registered_agents: LocalBridgeAgentState[];
  };
};

export default async function ConnectionsPage() {
  try {
    const [credResp, accResp, agentsResp, bridgeResp] = await Promise.all([
      apiGet<ListResponse<ConnectionsCredential>>("/credentials"),
      apiGet<ListResponse<ConnectionsAccount>>("/accounts").catch(() => ({
        items: [] as ConnectionsAccount[],
      })),
      apiGet<ListResponse<Agent>>("/agents"),
      apiGet<LocalBridgeResponse>("/local-bridge").catch(() => ({
        data: { registered_agents: [] as LocalBridgeAgentState[] },
      })),
    ]);

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
          bridgeAgents={bridgeResp.data?.registered_agents ?? []}
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
