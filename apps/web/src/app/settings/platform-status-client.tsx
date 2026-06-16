"use client";

import { useEffect, useState } from "react";

import { apiPost, safeApiGet } from "@/lib/api";
import { useT } from "@/lib/i18n/LocaleProvider";

type Capabilities = {
  platform?: { name?: string; version?: string; environment?: string };
  kanaloa?: {
    permissions?: string[];
    llm_configured?: boolean;
    permission_profile?: string;
  };
  agents?: { id?: string; name?: string; enabled?: boolean }[];
  bridge_probe?: { reachable?: boolean; probed_at?: string };
};

type TaskRow = { task_id?: string; title?: string; status?: string };

type AdapterBlock = {
  configured?: boolean;
  enabled?: boolean;
  available?: boolean;
  health?: string;
  details?: string;
  command?: string;
};

export function PlatformStatusClient() {
  const t = useT();
  const [cap, setCap] = useState<Capabilities | null>(null);
  const [localBridge, setLocalBridge] = useState<AdapterBlock | null>(null);
  const [claude, setClaude] = useState<AdapterBlock | null>(null);
  const [codex, setCodex] = useState<AdapterBlock | null>(null);
  const [cursor, setCursor] = useState<AdapterBlock | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tasks, setTasks] = useState<TaskRow[]>([]);
  const [actionNote, setActionNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refreshTasks = async () => {
    const r = await safeApiGet<{ items?: TaskRow[] }>("/tasks");
    if (!r.error && r.data?.items) {
      setTasks(r.data.items.slice(0, 8));
    }
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const c = await safeApiGet<Capabilities>("/api/system/capabilities");
      const a = await safeApiGet<{
        local_bridge?: AdapterBlock;
        claude_code?: AdapterBlock;
        codex_cli?: AdapterBlock;
        cursor?: AdapterBlock;
      }>("/api/adapters/status");
      if (cancelled) return;
      if (c.error) setError(c.error);
      else setCap(c.data);
      if (!a.error && a.data) {
        setLocalBridge(a.data.local_bridge ?? null);
        setClaude(a.data.claude_code ?? null);
        setCodex(a.data.codex_cli ?? null);
        setCursor(a.data.cursor ?? null);
      }
      await refreshTasks();
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const Row = ({ title, block }: { title: string; block: AdapterBlock | null }) => (
    <div className="rounded-lg border border-zinc-200 bg-white p-3 text-sm space-y-1">
      <div className="font-medium text-zinc-900">{title}</div>
      {block ? (
        <>
          <div className="grid grid-cols-2 gap-x-2 gap-y-1 text-xs">
            <span className="text-zinc-500">{t("settings.platform.configured")}</span>
            <span>{String(block.configured ?? "—")}</span>
            <span className="text-zinc-500">{t("settings.platform.enabled")}</span>
            <span>{String(block.enabled ?? "—")}</span>
            <span className="text-zinc-500">{t("settings.platform.health")}</span>
            <span className="font-mono">{block.health ?? "—"}</span>
          </div>
          {block.command ? (
            <div className="text-xs text-zinc-500">
              <span className="text-zinc-400">{t("settings.platform.command")}: </span>
              <code className="rounded bg-zinc-50 px-1">{block.command}</code>
            </div>
          ) : null}
          <p className="text-xs text-zinc-600 leading-relaxed">{block.details ?? "—"}</p>
        </>
      ) : (
        <p className="text-xs text-zinc-400">{t("settings.platform.loading")}</p>
      )}
    </div>
  );

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold">{t("settings.platform.title")}</h2>
        <p className="mt-1 text-xs text-zinc-500">{t("settings.platform.desc")}</p>
      </div>

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800">{error}</div>
      ) : null}

      <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3 text-xs space-y-1">
        <div>
          <span className="text-zinc-500">{t("settings.platform.permission_profile_label")}: </span>
          <span
            className={
              cap?.kanaloa?.permission_profile === "owner"
                ? "font-medium text-emerald-800"
                : cap?.kanaloa?.permission_profile === "safe"
                  ? "font-medium text-amber-800"
                  : cap?.kanaloa?.permission_profile === "readonly"
                    ? "font-medium text-zinc-700"
                    : "font-mono text-zinc-700"
            }
          >
            {cap?.kanaloa?.permission_profile === "owner"
              ? t("settings.platform.profile_owner")
              : cap?.kanaloa?.permission_profile === "safe"
                ? t("settings.platform.profile_safe")
                : cap?.kanaloa?.permission_profile === "readonly"
                  ? t("settings.platform.profile_readonly")
                  : "—"}
          </span>
        </div>
        <div>
          <span className="text-zinc-500">{t("settings.platform.api_version")}: </span>
          <span className="font-mono">{cap?.platform?.version ?? "—"}</span>
        </div>
        <div>
          <span className="text-zinc-500">{t("settings.platform.environment")}: </span>
          <span className="font-mono">{cap?.platform?.environment ?? "—"}</span>
        </div>
        <div>
          <span className="text-zinc-500">{t("settings.platform.llm")}: </span>
          <span>{cap?.kanaloa?.llm_configured ? t("settings.platform.llm_ok") : t("settings.platform.llm_missing")}</span>
        </div>
        <div>
          <span className="text-zinc-500">{t("settings.platform.last_probe")}: </span>
          <span className="font-mono text-[11px]">{cap?.bridge_probe?.probed_at ?? "—"}</span>
        </div>
      </div>

      <div>
        <h3 className="text-sm font-medium text-zinc-800 mb-2">{t("settings.platform.kanaloa_permissions")}</h3>
        <div className="flex flex-wrap gap-1">
          {(cap?.kanaloa?.permissions ?? []).slice(0, 48).map((p) => (
            <span key={p} className="rounded-full bg-white border border-zinc-200 px-2 py-0.5 text-[11px] font-mono">
              {p}
            </span>
          ))}
          {!cap?.kanaloa?.permissions?.length ? (
            <span className="text-xs text-zinc-400">{t("settings.platform.loading")}</span>
          ) : null}
        </div>
      </div>

      <div>
        <h3 className="text-sm font-medium text-zinc-800 mb-2">{t("settings.platform.agents_registered")}</h3>
        <ul className="text-xs space-y-1">
          {(cap?.agents ?? []).map((a) => (
            <li key={a.id} className="flex gap-2">
              <code className="font-mono">{a.id}</code>
              <span>{a.name}</span>
              <span className="text-zinc-400">{a.enabled ? "on" : "off"}</span>
            </li>
          ))}
          {!cap?.agents?.length ? <li className="text-zinc-400">{t("settings.platform.none")}</li> : null}
        </ul>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <Row title={t("settings.platform.bridge_title")} block={localBridge} />
        <Row title={t("settings.platform.claude_title")} block={claude} />
        <Row title={t("settings.platform.codex_title")} block={codex} />
        <Row title={t("settings.platform.cursor_title")} block={cursor} />
      </div>

      <div className="rounded-lg border border-zinc-200 bg-white p-3 space-y-2">
        <div className="text-sm font-medium text-zinc-900">{t("settings.platform.actions_title")}</div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy}
            className="rounded-md bg-zinc-900 px-3 py-1.5 text-xs text-white disabled:opacity-50"
            onClick={async () => {
              setBusy(true);
              setActionNote(null);
              try {
                const ag = await safeApiGet<{ items?: { agent_id?: string; adapter_id?: string | null }[] }>(
                  "/agents",
                );
                const cl = ag.data?.items?.find((x) => x.adapter_id === "claude_code");
                if (!cl?.agent_id) {
                  setActionNote(t("settings.platform.no_claude_agent"));
                  setBusy(false);
                  return;
                }
                const res = await apiPost<Record<string, unknown>>("/api/kanaloa/actions/create-task", {
                  agent_id: cl.agent_id,
                  instruction: "[Platform UI] Kanaloa dry_run probe",
                  mode: "dry_run",
                });
                setActionNote(JSON.stringify(res, null, 2));
                await refreshTasks();
              } catch (e) {
                setActionNote(e instanceof Error ? e.message : String(e));
              } finally {
                setBusy(false);
              }
            }}
          >
            {t("settings.platform.btn_dry_run")}
          </button>
          <button
            type="button"
            disabled={busy}
            className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs disabled:opacity-50"
            onClick={async () => {
              setBusy(true);
              setActionNote(null);
              try {
                const res = await apiPost<Record<string, unknown>>("/tasks", {
                  title: "[Platform UI] Kanaloa test task",
                  description: "Created from platform status panel",
                  execution_mode: "commander",
                  queue_priority: "normal",
                });
                setActionNote(JSON.stringify(res, null, 2));
                await refreshTasks();
              } catch (e) {
                setActionNote(e instanceof Error ? e.message : String(e));
              } finally {
                setBusy(false);
              }
            }}
          >
            {t("settings.platform.btn_create_task")}
          </button>
        </div>
        {actionNote ? (
          <pre className="mt-2 max-h-40 overflow-auto rounded bg-zinc-50 p-2 text-[11px] leading-snug">{actionNote}</pre>
        ) : null}
      </div>

      <div>
        <h3 className="text-sm font-medium text-zinc-800 mb-2">{t("settings.platform.recent_tasks")}</h3>
        <ul className="text-xs space-y-1 font-mono">
          {tasks.map((tk) => (
            <li key={tk.task_id}>
              {tk.task_id?.slice(0, 12)}… {String(tk.status ?? "")} — {tk.title}
            </li>
          ))}
          {!tasks.length ? <li className="text-zinc-400">{t("settings.platform.none")}</li> : null}
        </ul>
      </div>

      <p className="text-[11px] text-zinc-400">{t("settings.platform.footer_note")}</p>
    </div>
  );
}
