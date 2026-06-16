"use client";

import { useCallback, useEffect, useState } from "react";

import { safeApiGet } from "@/lib/api";
import { useT } from "@/lib/i18n/LocaleProvider";
import type { LocalBridgeAgentState } from "@/lib/octopus-types";

type AdapterBlock = {
  configured?: boolean;
  enabled?: boolean;
  available?: boolean;
  health?: string;
  details?: string;
  command?: string;
  url?: string | null;
  reachable?: boolean | null;
  probed_at?: string | null;
};

type AdaptersStatus = {
  local_bridge?: AdapterBlock;
  claude_code?: AdapterBlock;
  codex_cli?: AdapterBlock;
  cursor?: AdapterBlock;
  openclaw_http?: AdapterBlock;
};

const ROWS: Array<{ key: keyof AdaptersStatus; label: string }> = [
  { key: "local_bridge", label: "Local Bridge" },
  { key: "claude_code", label: "Claude Code" },
  { key: "codex_cli", label: "Codex" },
  { key: "cursor", label: "Cursor" },
  { key: "openclaw_http", label: "OpenClaw" },
];

function healthClass(health?: string): string {
  if (health === "ok") return "bg-emerald-100 text-emerald-800 border-emerald-200";
  if (health === "error") return "bg-red-100 text-red-800 border-red-200";
  return "bg-amber-100 text-amber-900 border-amber-200";
}

export function BridgeAdaptersStatusClient({
  registeredAgents = [],
}: {
  registeredAgents?: LocalBridgeAgentState[];
}) {
  const t = useT();
  const [status, setStatus] = useState<AdaptersStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    const res = await safeApiGet<AdaptersStatus>("/api/adapters/status");
    if (res.error) setError(res.error);
    else {
      setError(null);
      setStatus(res.data);
    }
    setBusy(false);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const res = await safeApiGet<AdaptersStatus>("/api/adapters/status");
      if (cancelled) return;
      if (res.error) setError(res.error);
      else {
        setError(null);
        setStatus(res.data);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section
      data-testid="bridge-adapters-status-card"
      className="rounded-lg border border-zinc-200 bg-white p-4"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-semibold">{t("bridge.adapters.title")}</div>
        <button
          type="button"
          disabled={busy}
          onClick={() => void load()}
          className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs text-zinc-700 disabled:opacity-50"
        >
          {busy ? t("bridge.adapters.refreshing") : t("bridge.adapters.refresh")}
        </button>
      </div>

      {error ? (
        <div className="mt-3 rounded-md border border-red-200 bg-red-50 p-3 text-xs text-red-800">
          {error}
        </div>
      ) : null}

      {registeredAgents.length > 0 ? (
        <div className="mt-3 space-y-2" data-testid="bridge-registered-agents-primary">
          <div className="text-xs font-medium text-zinc-700">{t("bridge.adapters.your_agents")}</div>
          {registeredAgents.map((agent) => (
            <div key={agent.state_id} className="rounded-md border border-sky-200 bg-sky-50 p-3">
              <div className="text-sm font-medium">{agent.display_name}</div>
              <div className="mt-1 text-xs text-zinc-600 font-mono">
                {agent.agent_id} · {agent.adapter_id} · {agent.status}
              </div>
            </div>
          ))}
        </div>
      ) : null}

      <details className="mt-3">
        <summary className="cursor-pointer text-xs text-zinc-600">{t("bridge.adapters.env_probe")}</summary>
        <div className="mt-2 space-y-2">
        {ROWS.map(({ key, label }) => {
          const block = status?.[key];
          return (
            <div
              key={key}
              data-testid={`bridge-adapter-${key}`}
              className="rounded-md border border-zinc-200 p-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-sm font-medium text-zinc-900">{label}</div>
                <span
                  className={`rounded-full border px-2 py-0.5 text-xs font-medium ${healthClass(block?.health)}`}
                >
                  {block?.health ?? "—"}
                </span>
              </div>
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-500">
                {key === "local_bridge" ? (
                  <span>{t("bridge.adapters.reachable")}: {String(block?.reachable ?? "—")}</span>
                ) : (
                  <>
                    <span>{t("bridge.adapters.configured")}: {String(block?.configured ?? "—")}</span>
                    <span>{t("bridge.adapters.available")}: {String(block?.available ?? "—")}</span>
                  </>
                )}
                {block?.command ? <span className="font-mono">{block.command}</span> : null}
              </div>
              {block?.details ? (
                <p className="mt-1 text-xs leading-relaxed text-zinc-600">{block.details}</p>
              ) : null}
            </div>
          );
        })}
        </div>
      </details>
    </section>
  );
}
