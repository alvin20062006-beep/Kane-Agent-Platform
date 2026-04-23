"use client";

import { BetaNotice } from "@/components/beta-notice";
import { JsonCard } from "@/components/json-card";
import { PageTitle } from "@/components/page-title";
import { useT } from "@/lib/i18n/LocaleProvider";
import type { LocalBridgeAgentState } from "@/lib/octopus-types";

import { BridgeConnectionWizard } from "./bridge-wizard-client";

type LocalBridgeResponseData = {
  url: string;
  reachable: boolean | null;
  registered_agents: LocalBridgeAgentState[];
  last_seen_at?: string | null;
  docs: string;
};

export function LocalBridgeClient({ data }: { data: LocalBridgeResponseData }) {
  const t = useT();
  return (
    <div className="space-y-6 p-6">
      <PageTitle title={t("bridge.title")} subtitle={t("bridge.subtitle")} />

      <BetaNotice note={t("bridge.beta_notice")} />

      <BridgeConnectionWizard
        initial={{
          url: data.url,
          reachable: data.reachable,
          last_seen_at: data.last_seen_at ?? null,
        }}
      />

      <section className="grid gap-4 md:grid-cols-3">
        <div data-testid="bridge-url-card" className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-xs text-zinc-600">{t("bridge.bridge_url")}</div>
          <div className="mt-2 text-sm font-medium">{data.url}</div>
        </div>
        <div data-testid="bridge-reachable-card" className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-xs text-zinc-600">{t("bridge.reachable")}</div>
          <div className="mt-2 text-sm font-medium">{String(data.reachable)}</div>
        </div>
        <div data-testid="bridge-last-seen-card" className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-xs text-zinc-600">{t("bridge.last_seen")}</div>
          <div className="mt-2 text-sm font-medium">{data.last_seen_at ?? t("dashboard.none")}</div>
        </div>
      </section>

      <section data-testid="bridge-agents-card" className="rounded-lg border border-zinc-200 bg-white p-4">
        <div className="text-sm font-semibold">{t("bridge.registered_agents")}</div>
        <div className="mt-3 space-y-3">
          {data.registered_agents.length ? (
            data.registered_agents.map((agent) => (
              <div
                data-testid={`bridge-agent-${agent.agent_id}`}
                key={agent.state_id}
                className="rounded-md border border-zinc-200 p-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="font-medium">{agent.display_name}</div>
                    <div className="mt-1 text-xs text-zinc-500">
                      {agent.agent_id} • {agent.adapter_id} • {agent.status}
                    </div>
                  </div>
                  <div className="text-xs text-zinc-500">
                    {t("bridge.seen_at")} {agent.last_seen_at}
                  </div>
                </div>
                <div className="mt-3">
                  <JsonCard data={agent} />
                </div>
              </div>
            ))
          ) : (
            <div className="text-sm text-zinc-500">{t("bridge.none_registered")}</div>
          )}
        </div>
      </section>
    </div>
  );
}

