"use client";

import { useCallback, useState } from "react";

import { apiPost } from "@/lib/api";
import { buildCallbackExample } from "@/lib/bridge-callback";
import { useT } from "@/lib/i18n/LocaleProvider";

export type BridgeRuntime = {
  reachable?: boolean | null;
  last_execute_at?: string | null;
  last_execute_error?: string | null;
  handoff_dir?: string | null;
  api_public_url?: string | null;
  probed_at?: string | null;
};

type ProbePayload = {
  version?: string;
  data: {
    reachable: boolean | null;
    api_public_url: string;
    bridge_status: {
      last_execute?: { at?: string | null; last_error?: string | null };
      handoff_dir?: string;
    } | null;
    probed_at: string;
  };
};

function extractRuntime(probe: ProbePayload["data"]): BridgeRuntime {
  const bs = probe.bridge_status ?? {};
  const le = bs.last_execute ?? {};
  return {
    reachable: probe.reachable,
    last_execute_at: le.at ?? null,
    last_execute_error: le.last_error ?? null,
    handoff_dir: bs.handoff_dir ?? null,
    api_public_url: probe.api_public_url,
    probed_at: probe.probed_at,
  };
}

function dash(value: string | null | undefined, none: string): string {
  return value && String(value).trim() ? String(value) : none;
}

export function BridgeRuntimeStatusClient({
  initial,
  highlightTaskId,
}: {
  initial: BridgeRuntime | null;
  highlightTaskId?: string | null;
}) {
  const t = useT();
  const [runtime, setRuntime] = useState<BridgeRuntime | null>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await apiPost<ProbePayload>("/local-bridge/probe", {});
      setRuntime(extractRuntime(res.data));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  const apiBase = runtime?.api_public_url ?? "http://127.0.0.1:8000";
  const none = t("dashboard.none");

  return (
    <section
      data-testid="bridge-runtime-status-card"
      className={`rounded-lg border bg-white p-4 ${
        highlightTaskId ? "border-sky-300 ring-1 ring-sky-100" : "border-zinc-200"
      }`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-semibold">{t("bridge.runtime.title")}</div>
        <button
          type="button"
          disabled={busy}
          data-testid="bridge-runtime-refresh"
          onClick={() => void refresh()}
          className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs text-zinc-700 disabled:opacity-50"
        >
          {busy ? t("bridge.adapters.refreshing") : t("bridge.adapters.refresh")}
        </button>
      </div>

      {error ? (
        <div className="mt-3 rounded-md border border-red-200 bg-red-50 p-3 text-xs text-red-800">{error}</div>
      ) : null}

      {runtime?.reachable === false ? (
        <p className="mt-3 text-xs text-amber-800">{t("bridge.runtime.unreachable_hint")}</p>
      ) : null}

      <dl className="mt-3 space-y-3 text-sm">
        <div data-testid="bridge-runtime-last-execute">
          <dt className="text-xs text-zinc-500">{t("bridge.runtime.last_execute")}</dt>
          <dd className="mt-1 font-mono text-xs break-all">{dash(runtime?.last_execute_at, none)}</dd>
        </div>
        <div data-testid="bridge-runtime-last-error">
          <dt className="text-xs text-zinc-500">{t("bridge.runtime.last_error")}</dt>
          <dd
            className={`mt-1 font-mono text-xs break-all ${
              runtime?.last_execute_error ? "text-red-700" : "text-zinc-700"
            }`}
          >
            {dash(runtime?.last_execute_error, none)}
          </dd>
        </div>
        {highlightTaskId ? (
          <div
            data-testid="bridge-runtime-task-highlight"
            className="rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-900"
          >
            {t("bridge.task_handoff_hint").replace("{taskId}", highlightTaskId)}
          </div>
        ) : null}
        <div data-testid="bridge-runtime-handoff-dir">
          <dt className="text-xs text-zinc-500">{t("bridge.runtime.handoff_dir")}</dt>
          <dd className="mt-1 font-mono text-xs break-all">{dash(runtime?.handoff_dir, none)}</dd>
        </div>
        <div data-testid="bridge-runtime-callback-example">
          <dt className="text-xs text-zinc-500">{t("bridge.runtime.callback_example")}</dt>
          <dd className="mt-1">
            <pre className="overflow-x-auto rounded-md border border-zinc-200 bg-zinc-50 p-3 text-[11px] leading-relaxed text-zinc-800">
              {buildCallbackExample(apiBase, highlightTaskId)}
            </pre>
          </dd>
        </div>
      </dl>
    </section>
  );
}
