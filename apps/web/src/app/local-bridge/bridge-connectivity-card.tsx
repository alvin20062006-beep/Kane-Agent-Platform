"use client";

import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";

import { apiPost, getApiBaseUrl } from "@/lib/api";
import { useT } from "@/lib/i18n/LocaleProvider";

type Initial = {
  url: string;
  reachable: boolean | null;
  last_seen_at?: string | null;
};

type ProbePayload = {
  version?: string;
  data: {
    url: string;
    api_public_url: string;
    reachable: boolean | null;
    error: string | null;
    health: unknown;
    bridge_status: unknown;
    hints: string[];
    probed_at: string;
  };
};

/** Shared Bridge connectivity probe (replaces standalone bridge-wizard). */
export function BridgeConnectivityCard({ initial }: { initial: Initial }) {
  const t = useT();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [lastProbe, setLastProbe] = useState<ProbePayload["data"] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const runProbe = useCallback(async () => {
    setBusy(true);
    setErr(null);
    try {
      const res = await apiPost<ProbePayload>("/local-bridge/probe", {});
      setLastProbe(res.data);
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [router]);

  const snapshot = lastProbe;
  const reachable = snapshot ? snapshot.reachable : initial.reachable;
  const showUrl = snapshot?.url ?? initial.url;

  return (
    <section
      className="rounded-lg border border-zinc-200 bg-white p-4 space-y-4"
      data-testid="bridge-wizard"
    >
      <div>
        <div className="text-sm font-semibold">{t("bridge.wizard.title")}</div>
        <p className="mt-1 text-xs text-zinc-600">{t("bridge.wizard.subtitle")}</p>
      </div>

      <div className="grid gap-3 md:grid-cols-2 text-sm">
        <div className="rounded-md border border-zinc-100 bg-zinc-50 p-3">
          <div className="text-xs text-zinc-500">{t("bridge.wizard.web_base")}</div>
          <div className="mt-1 font-mono text-xs break-all">{getApiBaseUrl()}</div>
        </div>
        <div className="rounded-md border border-zinc-100 bg-zinc-50 p-3">
          <div className="text-xs text-zinc-500">{t("bridge.wizard.bridge_url")}</div>
          <div className="mt-1 font-mono text-xs break-all">{showUrl}</div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={busy}
          data-testid="bridge-wizard-probe"
          onClick={() => void runProbe()}
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? t("bridge.wizard.probe_busy") : t("bridge.wizard.probe_btn")}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => router.refresh()}
          className="rounded-md border border-zinc-300 px-4 py-2 text-sm text-zinc-800"
        >
          {t("bridge.wizard.refresh")}
        </button>
      </div>

      <div
        className="rounded-md border border-zinc-200 p-3 text-sm"
        data-testid="bridge-wizard-connectivity"
      >
        <div className="text-xs font-medium text-zinc-500">{t("bridge.wizard.status_label")}</div>
        <div className="mt-2">
          <span
            data-testid="bridge-wizard-reachable-label"
            className={
              reachable === true
                ? "text-emerald-700 font-medium"
                : reachable === false
                ? "text-red-700 font-medium"
                : "text-zinc-600"
            }
          >
            {reachable === true ? "reachable" : reachable === false ? "unreachable" : "unknown"}
          </span>
          {snapshot?.probed_at ? (
            <span className="ml-2 text-xs text-zinc-500" data-testid="bridge-wizard-probe-at">
              {t("bridge.wizard.probed_at")} {snapshot.probed_at}
            </span>
          ) : (
            <span className="ml-2 text-xs text-zinc-500">
              {t("bridge.wizard.last_seen_snapshot")}: {initial.last_seen_at ?? "none"}{" "}
              {t("bridge.wizard.last_seen_hint")}
            </span>
          )}
        </div>
        {snapshot?.error ? (
          <div className="mt-2 text-xs text-red-700">
            {t("bridge.wizard.recent_error")}: {snapshot.error}
          </div>
        ) : null}
      </div>

      {err ? (
        <div className="text-sm text-red-700" data-testid="bridge-wizard-error">
          {err}
        </div>
      ) : null}

      {snapshot?.hints?.length ? (
        <div>
          <div className="text-xs font-medium text-zinc-600">{t("bridge.wizard.fix_suggestions")}</div>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-zinc-700">
            {snapshot.hints.map((h) => (
              <li key={h.slice(0, 80)}>{h}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
