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

const muted = "text-[var(--kane-muted)]";

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
    <div className="kane-card kane-grain space-y-2 p-4 text-sm">
      <div className="font-semibold text-[var(--kane-walnut)]">{title}</div>
      {block ? (
        <>
          <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
            <span className={muted}>{t("settings.platform.configured")}</span>
            <span>{String(block.configured ?? "-")}</span>
            <span className={muted}>{t("settings.platform.enabled")}</span>
            <span>{String(block.enabled ?? "-")}</span>
            <span className={muted}>{t("settings.platform.health")}</span>
            <span className="font-mono">{block.health ?? "-"}</span>
          </div>
          {block.command ? (
            <div className="text-xs text-[var(--kane-muted)]">
              <span>{t("settings.platform.command")}: </span>
              <code className="rounded bg-white/55 px-1">{block.command}</code>
            </div>
          ) : null}
          <p className="text-xs leading-relaxed text-[var(--kane-muted)]">{block.details ?? "-"}</p>
        </>
      ) : (
        <p className="text-xs text-[var(--kane-muted)]">{t("settings.platform.loading")}</p>
      )}
    </div>
  );

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold text-[var(--kane-walnut)]">{t("settings.platform.title")}</h2>
        <p className="mt-1 text-sm text-[var(--kane-muted)]">{t("settings.platform.desc")}</p>
      </div>

      {error ? (
        <div className="rounded-md border border-red-200 bg-[var(--kane-danger-soft)] p-3 text-xs text-[var(--kane-danger)]">
          {error}
        </div>
      ) : null}

      <div className="kane-card kane-grain space-y-2 p-5 text-xs">
        <div>
          <span className={muted}>{t("settings.platform.permission_profile_label")}: </span>
          <span
            className={
              cap?.kanaloa?.permission_profile === "owner"
                ? "font-semibold text-[var(--kane-moss)]"
                : cap?.kanaloa?.permission_profile === "safe"
                  ? "font-semibold text-[var(--kane-amber-deep)]"
                  : cap?.kanaloa?.permission_profile === "readonly"
                    ? "font-semibold text-[var(--kane-muted)]"
                    : "font-mono text-[var(--kane-muted)]"
            }
          >
            {cap?.kanaloa?.permission_profile === "owner"
              ? t("settings.platform.profile_owner")
              : cap?.kanaloa?.permission_profile === "safe"
                ? t("settings.platform.profile_safe")
                : cap?.kanaloa?.permission_profile === "readonly"
                  ? t("settings.platform.profile_readonly")
                  : "-"}
          </span>
        </div>
        <div>
          <span className={muted}>{t("settings.platform.api_version")}: </span>
          <span className="font-mono">{cap?.platform?.version ?? "-"}</span>
        </div>
        <div>
          <span className={muted}>{t("settings.platform.environment")}: </span>
          <span className="font-mono">{cap?.platform?.environment ?? "-"}</span>
        </div>
        <div>
          <span className={muted}>{t("settings.platform.llm")}: </span>
          <span>{cap?.kanaloa?.llm_configured ? t("settings.platform.llm_ok") : t("settings.platform.llm_missing")}</span>
        </div>
        <div>
          <span className={muted}>{t("settings.platform.last_probe")}: </span>
          <span className="font-mono text-[11px]">{cap?.bridge_probe?.probed_at ?? "-"}</span>
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-[var(--kane-walnut)]">
          {t("settings.platform.kanaloa_permissions")}
        </h3>
        <div className="flex flex-wrap gap-1.5">
          {(cap?.kanaloa?.permissions ?? []).slice(0, 48).map((p) => (
            <span key={p} className="rounded-full border border-[var(--kane-border)] bg-white/55 px-2 py-0.5 font-mono text-[11px]">
              {p}
            </span>
          ))}
          {!cap?.kanaloa?.permissions?.length ? (
            <span className="text-xs text-[var(--kane-muted)]">{t("settings.platform.loading")}</span>
          ) : null}
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-[var(--kane-walnut)]">
          {t("settings.platform.agents_registered")}
        </h3>
        <ul className="space-y-1 text-xs">
          {(cap?.agents ?? []).map((a) => (
            <li key={a.id} className="flex gap-2">
              <code className="font-mono">{a.id}</code>
              <span>{a.name}</span>
              <span className={a.enabled ? "text-[var(--kane-moss)]" : "text-[var(--kane-muted)]"}>
                {a.enabled ? "on" : "off"}
              </span>
            </li>
          ))}
          {!cap?.agents?.length ? <li className="text-[var(--kane-muted)]">{t("settings.platform.none")}</li> : null}
        </ul>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <Row title={t("settings.platform.bridge_title")} block={localBridge} />
        <Row title={t("settings.platform.claude_title")} block={claude} />
        <Row title={t("settings.platform.codex_title")} block={codex} />
        <Row title={t("settings.platform.cursor_title")} block={cursor} />
      </div>

      <div className="kane-card kane-grain space-y-3 p-5">
        <div className="text-sm font-semibold text-[var(--kane-walnut)]">
          {t("settings.platform.actions_title")}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy}
            className="rounded-md bg-[linear-gradient(180deg,var(--kane-walnut),var(--kane-walnut-deep))] px-3.5 py-2 text-xs text-white shadow-[0_8px_18px_rgba(81,39,7,0.18)] disabled:opacity-50"
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
            className="rounded-md border border-[var(--kane-border)] bg-white/55 px-3.5 py-2 text-xs shadow-[0_1px_0_rgba(255,255,255,0.6)_inset] disabled:opacity-50"
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
          <pre className="mt-2 max-h-40 overflow-auto rounded-md border border-[var(--kane-border)] bg-white/55 p-3 text-[11px] leading-snug">
            {actionNote}
          </pre>
        ) : null}
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-[var(--kane-walnut)]">
          {t("settings.platform.recent_tasks")}
        </h3>
        <ul className="space-y-1 font-mono text-xs">
          {tasks.map((tk) => (
            <li key={tk.task_id}>
              {tk.task_id?.slice(0, 12)} - {String(tk.status ?? "")} - {tk.title}
            </li>
          ))}
          {!tasks.length ? <li className="text-[var(--kane-muted)]">{t("settings.platform.none")}</li> : null}
        </ul>
      </div>

      <p className="text-[11px] text-[var(--kane-muted)]">{t("settings.platform.footer_note")}</p>
    </div>
  );
}
