"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { apiDelete, apiGet, apiPatch, apiPost } from "@/lib/api";
import { useT } from "@/lib/i18n/LocaleProvider";
import type {
  Agent,
  ApiProfile,
  ListResponse,
  LocalBridgeAgentState,
} from "@/lib/octopus-types";

export type FleetDetail = {
  data: Agent;
  bridge_state?: LocalBridgeAgentState | null;
};

function badge(text: string, tone: "ok" | "warn" | "bad" | "neutral") {
  const cls =
    tone === "ok"
      ? "border-emerald-200 bg-[var(--kane-moss-soft)] text-[var(--kane-moss)]"
      : tone === "warn"
        ? "border-amber-200 bg-[var(--kane-amber-soft)] text-[var(--kane-amber-deep)]"
        : tone === "bad"
          ? "border-red-200 bg-[var(--kane-danger-soft)] text-[var(--kane-danger)]"
          : "border-[var(--kane-border)] bg-white/55 text-[var(--foreground)]";
  return (
    <span className={`rounded-full border px-2.5 py-1 text-[var(--kane-caption-size)] font-medium ${cls}`}>
      {text}
    </span>
  );
}

type MenuItem =
  | {
      label: string;
      onClick: () => void;
      danger?: boolean;
      disabled?: boolean;
      hint?: string;
    }
  | { separator: true };

function RowMenu({ items, align = "right" }: { items: MenuItem[]; align?: "left" | "right" }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--kane-muted)] hover:bg-[var(--kane-amber-soft)] hover:text-[var(--kane-walnut)]"
        aria-label="more"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
          <circle cx="5" cy="12" r="2" />
          <circle cx="12" cy="12" r="2" />
          <circle cx="19" cy="12" r="2" />
        </svg>
      </button>
      {open && (
        <div
          role="menu"
          className={`absolute z-40 mt-1 min-w-[200px] rounded-md border border-[var(--kane-border)] bg-[var(--kane-paper)] py-1 shadow-lg ${
            align === "right" ? "right-0" : "left-0"
          }`}
        >
          {items.map((item, idx) => {
            if ("separator" in item) {
              return <div key={idx} className="my-1 border-t border-[var(--kane-border)]" />;
            }
            return (
              <button
                key={idx}
                type="button"
                role="menuitem"
                disabled={item.disabled}
                onClick={() => {
                  setOpen(false);
                  item.onClick();
                }}
                title={item.hint}
                className={`flex w-full items-center justify-between px-3 py-1.5 text-left text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                  item.danger
                    ? "text-[var(--kane-danger)] hover:bg-[var(--kane-danger-soft)]"
                    : "text-[var(--foreground)] hover:bg-white/70"
                }`}
              >
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function BindProfileDialog({
  agent,
  onClose,
  onDone,
}: {
  agent: Agent;
  onClose: () => void;
  onDone: () => void;
}) {
  const t = useT();
  const [profiles, setProfiles] = useState<ApiProfile[]>([]);
  const [pid, setPid] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    apiGet<ListResponse<ApiProfile>>("/api-profiles")
      .then((r) => setProfiles(r.items))
      .catch((e) => setErr(String(e)));
  }, []);

  const bind = async () => {
    if (!pid) return;
    setBusy(true);
    setErr(null);
    try {
      await apiPost(`/agents/${encodeURIComponent(agent.agent_id)}/api-profile`, {
        profile_id: pid,
      });
      onDone();
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/30" onClick={onClose} aria-hidden />
      <div
        role="dialog"
        aria-modal="true"
        className="kane-card fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 shadow-xl"
      >
        <div className="space-y-3 p-5">
          <div className="text-sm font-semibold text-[var(--kane-walnut)]">
            {t("action.bind_profile")}
          </div>
          <div className="text-xs text-[var(--kane-muted)]">
            {agent.display_name} <span className="font-mono">({agent.agent_id})</span>
          </div>
          {err && (
            <div className="rounded-md border border-red-200 bg-[var(--kane-danger-soft)] px-3 py-2 text-xs text-[var(--kane-danger)]">
              {err}
            </div>
          )}
          <select
            value={pid}
            onChange={(e) => setPid(e.target.value)}
            className="w-full rounded-md border border-[var(--kane-border)] bg-white/75 px-3 py-2 text-sm text-[var(--foreground)]"
          >
            <option value="">-</option>
            {profiles.map((p) => (
              <option key={p.profile_id} value={p.profile_id}>
                {p.name} - {p.provider} - {p.model}
                {p.is_default ? " (default)" : ""}
              </option>
            ))}
          </select>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="kane-button-secondary rounded-md px-3 py-1.5 text-xs hover:bg-white"
            >
              {t("action.cancel")}
            </button>
            <button
              type="button"
              disabled={busy || !pid}
              onClick={bind}
              className="rounded-md bg-[var(--kane-walnut)] px-3 py-1.5 text-xs text-white disabled:opacity-50"
            >
              {busy ? t("common.saving") : t("action.save")}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

export function AgentFleetClusterView({ details }: { details: FleetDetail[] }) {
  const t = useT();
  const [rowsData, setRowsData] = useState<FleetDetail[]>(details);
  const [onlyConnected, setOnlyConnected] = useState(false);
  const [onlyCode, setOnlyCode] = useState(false);
  const [onlyProblems, setOnlyProblems] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [bindTarget, setBindTarget] = useState<Agent | null>(null);

  const refresh = async () => {
    try {
      const list = await apiGet<ListResponse<Agent>>("/agents");
      const enriched = await Promise.all(
        list.items.map(async (agent) => {
          try {
            const d = await apiGet<FleetDetail>(
              `/agents/${encodeURIComponent(agent.agent_id)}`
            );
            return d;
          } catch {
            return { data: agent, bridge_state: null };
          }
        })
      );
      setRowsData(enriched);
    } catch (e) {
      setToast(e instanceof Error ? e.message : String(e));
    }
  };

  const flash = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  };

  const rows = useMemo(() => {
    return rowsData.filter(({ data, bridge_state }) => {
      const connected = Boolean(bridge_state);
      const code = Boolean(data.capabilities?.can_code);
      const prob =
        data.status === "degraded" || data.status === "offline" || data.status === "stalled";
      if (onlyConnected && !connected && data.type === "external") return false;
      if (onlyCode && !code) return false;
      if (onlyProblems && !prob) return false;
      return true;
    });
  }, [rowsData, onlyConnected, onlyCode, onlyProblems]);

  const testRun = async (agent: Agent) => {
    setBusy(agent.agent_id);
    try {
      const res = await apiPost<{
        task_id?: string;
        task_status?: string;
        ok?: boolean;
      }>(`/agents/${encodeURIComponent(agent.agent_id)}/test-run`);
      flash(`Test run -> ${res.task_status ?? "queued"} (task ${res.task_id ?? "?"})`);
    } catch (e) {
      flash(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const toggleEnabled = async (agent: Agent) => {
    const nextEnabled = !(agent.enabled ?? true);
    setBusy(agent.agent_id);
    try {
      await apiPatch(`/agents/${encodeURIComponent(agent.agent_id)}`, {
        enabled: nextEnabled,
      });
      await refresh();
      flash(nextEnabled ? t("action.enable") : t("action.disable"));
    } catch (e) {
      flash(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const deleteAgent = async (agent: Agent) => {
    if (agent.type === "builtin" || agent.adapter_id === "builtin_octopus") {
      flash(t("agents.builtin_cannot_delete"));
      return;
    }
    if (!confirm(`${t("action.delete")} ${agent.display_name}?`)) return;
    setBusy(agent.agent_id);
    try {
      await apiDelete(`/agents/${encodeURIComponent(agent.agent_id)}`);
      await refresh();
      flash(t("action.delete"));
    } catch (e) {
      flash(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-[var(--kane-section-gap)]">
      <div className="flex flex-wrap gap-x-6 gap-y-3 text-[var(--kane-body-size)] text-[var(--foreground)]">
        <label className="flex items-center gap-2">
          <input
            className="kane-checkbox h-4 w-4"
            type="checkbox"
            checked={onlyConnected}
            onChange={(e) => setOnlyConnected(e.target.checked)}
          />
          {t("agents.filter_connected")}
        </label>
        <label className="flex items-center gap-2">
          <input
            className="kane-checkbox h-4 w-4"
            type="checkbox"
            checked={onlyCode}
            onChange={(e) => setOnlyCode(e.target.checked)}
          />
          {t("agents.filter_code")}
        </label>
        <label className="flex items-center gap-2">
          <input
            className="kane-checkbox h-4 w-4"
            type="checkbox"
            checked={onlyProblems}
            onChange={(e) => setOnlyProblems(e.target.checked)}
          />
          {t("agents.filter_problems")}
        </label>
      </div>

      {toast && (
        <div className="kane-paper px-3 py-2 text-xs text-[var(--kane-muted)]">
          {toast}
        </div>
      )}

      <div className="grid gap-[var(--kane-section-gap)] lg:grid-cols-2">
        {rows.map(({ data, bridge_state }) => {
          const connected = data.type === "builtin" ? true : Boolean(bridge_state);
          const mode =
            data.integration_mode ?? (data.type === "builtin" ? "embedded" : "external");
          const depth = data.control_depth ?? "-";
          const channels = (data.integration_channels ?? []).join(", ") || "-";
          const code = data.capabilities?.can_code;
          const browse = data.capabilities?.can_browse;
          const general = data.capabilities?.supports_structured_task;
          const enabled = data.enabled ?? true;
          const isBuiltin = data.type === "builtin" || data.adapter_id === "builtin_octopus";

          return (
            <div
              key={data.agent_id}
              className={`kane-card space-y-4 p-[var(--kane-card-pad)] ${enabled ? "" : "opacity-70"}`}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-[1rem] font-semibold leading-tight text-[var(--kane-walnut)]">
                    {data.display_name}
                  </div>
                  <div className="mt-1 truncate font-mono text-[var(--kane-caption-size)] text-[var(--kane-muted)]">
                    {data.agent_id}
                  </div>
                </div>
                <div className="flex items-start gap-1">
                  <div className="flex flex-wrap gap-1.5">
                    {badge(
                      data.status,
                      data.status === "idle"
                        ? "neutral"
                        : data.status === "running"
                          ? "ok"
                          : data.status === "offline"
                            ? "bad"
                            : "warn"
                    )}
                    {badge(
                      connected ? t("agents.connected") : t("agents.disconnected"),
                      connected ? "ok" : "warn"
                    )}
                    {badge(mode, mode === "embedded" ? "ok" : "neutral")}
                    {!enabled && badge(t("skills.badge_disabled"), "neutral")}
                  </div>
                  <RowMenu
                    items={[
                      {
                        label: t("action.test_run"),
                        onClick: () => testRun(data),
                        disabled: busy === data.agent_id,
                      },
                      {
                        label: enabled ? t("action.disable") : t("action.enable"),
                        onClick: () => toggleEnabled(data),
                        disabled: busy === data.agent_id,
                      },
                      { separator: true },
                      {
                        label: t("action.configure"),
                        onClick: () => {
                          window.location.href = `/agent-fleet/${encodeURIComponent(
                            data.agent_id
                          )}`;
                        },
                      },
                      {
                        label: t("action.bind_profile"),
                        onClick: () => setBindTarget(data),
                      },
                      { separator: true },
                      {
                        label: t("action.delete"),
                        onClick: () => deleteAgent(data),
                        danger: true,
                        disabled: isBuiltin || busy === data.agent_id,
                        hint: isBuiltin ? t("agents.builtin_cannot_delete") : undefined,
                      },
                    ]}
                  />
                </div>
              </div>

              <div className="space-y-2 text-[var(--kane-body-size)] text-[var(--foreground)]">
                <div>
                  <span className="text-[var(--kane-muted)]">{t("agents.adapter")}:</span>{" "}
                  <span className="font-mono text-[var(--kane-caption-size)]">{data.adapter_id ?? "-"}</span>
                </div>
                <div>
                  <span className="text-[var(--kane-muted)]">{t("agents.control_depth")}:</span>{" "}
                  {depth}
                </div>
                <div>
                  <span className="text-[var(--kane-muted)]">{t("agents.channels")}:</span>{" "}
                  {channels}
                </div>
                <div>
                  <span className="text-[var(--kane-muted)]">{t("agents.last_heartbeat")}:</span>{" "}
                  <span className="font-mono text-[var(--kane-caption-size)]">{data.last_heartbeat_at ?? "-"}</span>
                </div>
                <div>
                  <span className="text-[var(--kane-muted)]">{t("agents.fits_for")}:</span>{" "}
                  {[code ? "code" : null, browse ? "browser" : null, general ? "structured" : null]
                    .filter(Boolean)
                    .join(" - ") || "-"}
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <Link
                  href={`/agent-fleet/${encodeURIComponent(data.agent_id)}`}
                  className="kane-button-primary rounded-[var(--kane-radius-control)] px-3.5 py-2 text-[var(--kane-caption-size)] font-medium"
                >
                  {t("agents.config_testrun")}
                </Link>
                <Link
                  href="/cockpit"
                  className="kane-button-secondary rounded-[var(--kane-radius-control)] px-3.5 py-2 text-[var(--kane-caption-size)]"
                >
                  {t("agents.send_task")}
                </Link>
              </div>
            </div>
          );
        })}
      </div>

      {bindTarget && (
        <BindProfileDialog
          agent={bindTarget}
          onClose={() => setBindTarget(null)}
          onDone={() => {
            void refresh();
            flash(t("action.bind_profile"));
          }}
        />
      )}
    </div>
  );
}
