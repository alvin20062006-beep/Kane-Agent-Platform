"use client";

import { ProductNotice } from "@/components/product-notice";
import { JsonCard } from "@/components/json-card";
import { PageTitle } from "@/components/page-title";
import { useT } from "@/lib/i18n/LocaleProvider";
import type { LocalBridgeAgentState } from "@/lib/octopus-types";

import { BridgeAdaptersStatusClient } from "./bridge-adapters-status-client";
import { BridgeConnectivityCard } from "./bridge-connectivity-card";
import { BridgeRuntimeStatusClient, type BridgeRuntime } from "./bridge-runtime-status-client";
import { ConnectAgentWizard } from "./connect-agent-wizard-client";

type LocalBridgeResponseData = {
  url: string;
  reachable: boolean | null;
  registered_agents: LocalBridgeAgentState[];
  last_seen_at?: string | null;
  recent_callback_audit?: Array<{
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
  }>;
  docs: string;
  bridge_runtime?: BridgeRuntime | null;
};

export function LocalBridgeClient({
  data,
  highlightTaskId,
  openConnectWizard = false,
}: {
  data: LocalBridgeResponseData;
  highlightTaskId?: string | null;
  openConnectWizard?: boolean;
}) {
  const t = useT();
  return (
    <div className="space-y-6 p-6">
      <PageTitle title={t("bridge.title")} subtitle={t("bridge.subtitle")} />

      {highlightTaskId ? (
        <div className="rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-900">
          {t("bridge.task_context").replace("{taskId}", highlightTaskId)}
        </div>
      ) : null}

      <ProductNotice note={t("bridge.notice")} />

      <ConnectAgentWizard defaultOpen={openConnectWizard} />

      <section className="rounded-lg border border-zinc-200 bg-white p-4">
        <div className="text-sm font-semibold">{t("bridge.integration_title")}</div>
        <p className="mt-2 text-sm text-zinc-700">{t("bridge.scope_intro")}</p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-zinc-700">
          <li>{t("bridge.scope_http_agent")}</li>
          <li>{t("bridge.scope_cli_agent")}</li>
          <li>{t("bridge.scope_handoff")}</li>
        </ul>
        <p className="mt-3 text-xs font-medium text-zinc-500">{t("bridge.scope_presets_title")}</p>
        <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-zinc-600">
          <li>{t("bridge.scope_claude")}</li>
          <li>{t("bridge.scope_codex")}</li>
          <li>{t("bridge.scope_cursor")}</li>
          <li>{t("bridge.scope_openclaw")}</li>
          <li>{t("bridge.scope_local_script")}</li>
        </ul>
      </section>

      <BridgeAdaptersStatusClient registeredAgents={data.registered_agents} />

      <BridgeRuntimeStatusClient
        initial={data.bridge_runtime ?? null}
        highlightTaskId={highlightTaskId}
      />

      <BridgeConnectivityCard
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

      <section data-testid="bridge-callback-audit-card" className="rounded-lg border border-zinc-200 bg-white p-4">
        <div className="text-sm font-semibold">Recent callback audit</div>
        <div className="mt-2 text-sm text-zinc-600">
          Bridge main state stays conservative. Rejected, duplicate, and late callbacks are shown here without
          mutating the registered agent status card above.
        </div>
        <div className="mt-3 space-y-3">
          {(data.recent_callback_audit ?? []).length ? (
            data.recent_callback_audit!.map((item, index) => (
              <div
                key={`${item.kind}-${item.run_id ?? "none"}-${index}`}
                className={`rounded-md border p-3 ${
                  highlightTaskId && item.task_id === highlightTaskId
                    ? "border-sky-300 bg-sky-50"
                    : "border-zinc-200"
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="font-medium">
                    {item.kind} • {item.status ?? "n/a"}
                  </div>
                  <div className="text-xs text-zinc-500">{item.created_at}</div>
                </div>
                <div className="mt-2 grid gap-2 text-xs text-zinc-600 md:grid-cols-2">
                  <div>agent: {item.agent_id ?? "n/a"}</div>
                  <div>path: {item.integration_path ?? "n/a"}</div>
                  <div>task: {item.task_id ?? "n/a"}</div>
                  <div>run: {item.run_id ?? "n/a"}</div>
                </div>
                {item.message ? <div className="mt-2 text-sm text-zinc-700">{item.message}</div> : null}
              </div>
            ))
          ) : (
            <div className="text-sm text-zinc-500">No recent callback audit events yet.</div>
          )}
        </div>
      </section>
    </div>
  );
}

