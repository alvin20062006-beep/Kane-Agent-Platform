"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ProductNotice } from "@/components/product-notice";
import { PageTitle } from "@/components/page-title";
import { useLocale, useT } from "@/lib/i18n/LocaleProvider";
import { masterIsActive, subtaskProgress } from "@/lib/task-completion";

import { apiPost, safeApiGet } from "@/lib/api";

type SubtaskRow = {
  subtask_id?: string;
  title?: string;
  status?: string;
  target_agent_id?: string | null;
  platform_task_id?: string | null;
  attempt_count?: number;
};

type MasterRow = {
  master_task_id?: string;
  status?: string;
  user_instruction?: string;
  created_at?: string;
  subtasks?: SubtaskRow[];
  final_summary?: string | null;
};

type OrchEvent = { type?: string; message?: string; created_at?: string };

type RunAccepted = {
  ok?: boolean;
  master_task_id?: string;
  status?: string;
  message?: string;
};

type SubtaskMode = "dry_run" | "execute";

function statusBadgeClass(status: string | undefined): string {
  const s = (status ?? "").toLowerCase();
  if (s === "completed" || s === "succeeded") return "bg-emerald-100 text-emerald-800";
  if (s === "failed" || s === "cancelled") return "bg-rose-100 text-rose-800";
  if (s === "running" || s === "queued" || s === "pending") return "bg-sky-100 text-sky-800";
  return "bg-zinc-100 text-zinc-700";
}

async function pollMasterUntilTerminal(masterTaskId: string): Promise<MasterRow | null> {
  const deadline = Date.now() + 180_000;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 2000));
    const g = await safeApiGet<{ master?: MasterRow }>(
      `/api/kanaloa/orchestrator/tasks/${encodeURIComponent(masterTaskId)}`,
    );
    const st = g.data?.master?.status;
    if (st === "completed" || st === "failed" || st === "cancelled") {
      return g.data?.master ?? null;
    }
  }
  return null;
}

export function OrchestratorClient() {
  const t = useT();
  const { locale } = useLocale();
  const searchParams = useSearchParams();
  const highlightMaster = searchParams.get("master");
  const [profile, setProfile] = useState<string>("—");
  const [items, setItems] = useState<MasterRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);
  const [polling, setPolling] = useState(false);
  const [instruction, setInstruction] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [eventsByMaster, setEventsByMaster] = useState<Record<string, OrchEvent[]>>({});

  useEffect(() => {
    setInstruction(t("orchestrator.example_instruction"));
  }, [locale, t]);

  const refresh = useCallback(async () => {
    const cap = await safeApiGet<{ kanaloa?: { permission_profile?: string } }>("/api/system/capabilities");
    if (!cap.error && cap.data?.kanaloa?.permission_profile) {
      setProfile(cap.data.kanaloa.permission_profile);
    }
    const list = await safeApiGet<{ items?: MasterRow[] }>("/api/kanaloa/orchestrator/tasks?limit=15");
    if (!list.error && list.data?.items) {
      setItems(list.data.items);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!highlightMaster || !items.length) return;
    const found = items.find((m) => m.master_task_id === highlightMaster);
    if (!found) return;
    setExpandedId(highlightMaster);
    void (async () => {
      const res = await safeApiGet<{ events?: OrchEvent[] }>(
        `/api/kanaloa/orchestrator/tasks/${encodeURIComponent(highlightMaster)}/events`,
      );
      if (!res.error && res.data?.events) {
        setEventsByMaster((prev) => ({ ...prev, [highlightMaster]: res.data!.events! }));
      }
    })();
    const el = document.querySelector(`[data-master-id="${highlightMaster}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [highlightMaster, items]);

  const hasActive = items.some((m) => masterIsActive(m.status));

  useEffect(() => {
    if (!hasActive) return;
    const id = window.setInterval(() => {
      void refresh();
    }, 3000);
    return () => window.clearInterval(id);
  }, [hasActive, refresh]);

  const loadEvents = async (masterId: string) => {
    if (expandedId === masterId) {
      setExpandedId(null);
      return;
    }
    setExpandedId(masterId);
    const res = await safeApiGet<{ events?: OrchEvent[] }>(
      `/api/kanaloa/orchestrator/tasks/${encodeURIComponent(masterId)}/events`,
    );
    if (!res.error && res.data?.events) {
      setEventsByMaster((prev) => ({ ...prev, [masterId]: res.data!.events! }));
    }
  };

  const run = async (mode: SubtaskMode, preset?: string) => {
    setBusy(true);
    setNote(null);
    setPolling(false);
    try {
      const body = {
        instruction: preset ?? instruction,
        subtask_mode: mode,
      };
      const res = await apiPost<RunAccepted>("/api/kanaloa/orchestrator/run", body);
      setNote(JSON.stringify(res, null, 2));
      const mid = res.master_task_id;
      if (mid) {
        setPolling(true);
        void (async () => {
          const done = await pollMasterUntilTerminal(mid);
          if (done) {
            setNote(JSON.stringify(done, null, 2));
          }
          setPolling(false);
          await refresh();
        })();
      } else {
        await refresh();
      }
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const continueLast = async (mode: SubtaskMode = "dry_run") => {
    const first = items[0];
    if (!first?.master_task_id) {
      setNote(t("orchestrator.err_no_master"));
      return;
    }
    setBusy(true);
    setNote(null);
    try {
      const res = await apiPost<RunAccepted>(
        `/api/kanaloa/orchestrator/tasks/${encodeURIComponent(first.master_task_id)}/continue`,
        { subtask_mode: mode },
      );
      setNote(JSON.stringify(res, null, 2));
      const mid = res.master_task_id ?? first.master_task_id;
      setPolling(true);
      void (async () => {
        const done = await pollMasterUntilTerminal(mid);
        if (done) setNote(JSON.stringify(done, null, 2));
        setPolling(false);
        await refresh();
      })();
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const cancelMaster = async (masterId: string) => {
    setBusy(true);
    setNote(null);
    try {
      const res = await apiPost<Record<string, unknown>>(
        `/api/kanaloa/orchestrator/tasks/${encodeURIComponent(masterId)}/cancel`,
        {},
      );
      setNote(JSON.stringify(res, null, 2));
      await refresh();
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const continueMaster = async (masterId: string, mode: SubtaskMode = "dry_run") => {
    setBusy(true);
    setNote(null);
    try {
      const res = await apiPost<RunAccepted>(
        `/api/kanaloa/orchestrator/tasks/${encodeURIComponent(masterId)}/continue`,
        { subtask_mode: mode },
      );
      setNote(JSON.stringify(res, null, 2));
      const mid = res.master_task_id ?? masterId;
      setPolling(true);
      void (async () => {
        const done = await pollMasterUntilTerminal(mid);
        if (done) setNote(JSON.stringify(done, null, 2));
        setPolling(false);
        await refresh();
      })();
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const cancelFirst = async () => {
    const first = items[0];
    if (!first?.master_task_id) return;
    await cancelMaster(first.master_task_id);
  };

  return (
    <div className="space-y-6 p-6">
      <PageTitle title={t("nav.orchestrator")} subtitle={t("orchestrator.desc")} />
      <ProductNotice note={t("orchestrator.notice")} />

      <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
        {t("orchestrator.mode_dry_hint")}
      </div>

      <div className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs">
        <span className="text-zinc-500">{t("settings.platform.permission_profile_label")}: </span>
        <span className="font-mono font-medium text-emerald-900">{profile}</span>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          className="rounded-md bg-zinc-900 px-3 py-2 text-xs text-white disabled:opacity-50"
          onClick={() => void run("dry_run", t("orchestrator.preset_audit_instruction"))}
        >
          {t("orchestrator.btn_audit")}
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded-md border border-zinc-300 px-3 py-2 text-xs disabled:opacity-50"
          onClick={() => void run("dry_run")}
        >
          {t("orchestrator.btn_custom_dry")}
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded-md border border-emerald-300 px-3 py-2 text-xs text-emerald-900 disabled:opacity-50"
          onClick={() => void run("execute")}
        >
          {t("orchestrator.btn_execute")}
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded-md border border-zinc-300 px-3 py-2 text-xs disabled:opacity-50"
          onClick={() => void continueLast("dry_run")}
        >
          {t("orchestrator.btn_continue")}
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded-md border border-red-200 px-3 py-2 text-xs text-red-900 disabled:opacity-50"
          onClick={() => void cancelFirst()}
        >
          {t("orchestrator.btn_cancel")}
        </button>
      </div>

      <div>
        <label className="text-xs font-medium text-zinc-600">{t("orchestrator.instruction_label")}</label>
        <textarea
          className="mt-1 w-full min-h-[100px] rounded border border-zinc-200 p-2 text-sm"
          value={instruction}
          placeholder={t("orchestrator.example_instruction")}
          onChange={(e) => setInstruction(e.target.value)}
        />
      </div>

      {polling ? (
        <div className="text-xs text-sky-700">{t("orchestrator.in_progress")}</div>
      ) : null}

      {note ? (
        <div>
          <button
            type="button"
            className="text-xs text-zinc-500 underline"
            onClick={() => setShowRaw((v) => !v)}
          >
            {showRaw ? t("orchestrator.hide_raw") : t("orchestrator.show_raw")}
          </button>
          {showRaw ? (
            <pre className="mt-2 max-h-64 overflow-auto rounded border border-zinc-100 bg-zinc-950 p-3 text-[11px] text-zinc-100">
              {note}
            </pre>
          ) : null}
        </div>
      ) : null}

      <div>
        <h2 className="text-sm font-medium text-zinc-800">{t("orchestrator.recent_masters")}</h2>
        <ul className="mt-2 space-y-3 text-xs">
          {items.map((m) => {
            const mid = m.master_task_id ?? "";
            const subs = m.subtasks ?? [];
            const prog = subtaskProgress(subs);
            return (
              <li
                key={mid}
                data-master-id={mid}
                className={`rounded-lg border bg-white p-3 ${
                  highlightMaster === mid ? "border-sky-400 ring-2 ring-sky-100" : "border-zinc-200"
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <span className="text-[10px] font-semibold uppercase tracking-wide text-zinc-400">
                      {t("orchestrator.work_order")}
                    </span>
                    <div className="font-mono text-[11px] text-zinc-500">{mid}</div>
                  </div>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${statusBadgeClass(m.status)}`}>
                    {m.status}
                  </span>
                </div>
                <p className="mt-1 text-zinc-600 line-clamp-2">{m.user_instruction}</p>
                {subs.length > 0 ? (
                  <div className="mt-2">
                    <div className="flex justify-between text-[10px] text-zinc-500">
                      <span>{t("orchestrator.progress")}</span>
                      <span>
                        {prog.done}/{prog.total} ({prog.pct}%)
                      </span>
                    </div>
                    <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-zinc-100">
                      <div
                        className="h-full rounded-full bg-emerald-500 transition-all"
                        style={{ width: `${prog.pct}%` }}
                      />
                    </div>
                  </div>
                ) : null}
                <ul className="mt-2 space-y-1.5 border-t border-zinc-100 pt-2">
                  {subs.map((s) => (
                    <li key={s.subtask_id} className="flex flex-wrap items-center gap-2">
                      <span className="text-[10px] uppercase text-zinc-400">{t("orchestrator.step")}</span>
                      <span className="font-medium">{s.title}</span>
                      <span className={`rounded px-1.5 py-0.5 text-[10px] ${statusBadgeClass(s.status)}`}>
                        {s.status}
                      </span>
                      {s.attempt_count != null && s.attempt_count > 0 ? (
                        <span className="text-zinc-400">attempts={s.attempt_count}</span>
                      ) : null}
                      {s.platform_task_id ? (
                        <Link
                          href={`/tasks/${encodeURIComponent(s.platform_task_id)}`}
                          className="font-mono text-[10px] text-sky-700 underline"
                        >
                          {t("orchestrator.link_task")}
                        </Link>
                      ) : null}
                    </li>
                  ))}
                </ul>
                {mid && masterIsActive(m.status) ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={busy}
                      data-testid={`orchestrator-continue-${mid}`}
                      className="rounded border border-zinc-300 px-2 py-1 text-[10px] disabled:opacity-50"
                      onClick={() => void continueMaster(mid, "dry_run")}
                    >
                      {t("orchestrator.btn_continue")}
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      className="rounded border border-red-200 px-2 py-1 text-[10px] text-red-800 disabled:opacity-50"
                      onClick={() => void cancelMaster(mid)}
                    >
                      {t("orchestrator.btn_cancel")}
                    </button>
                  </div>
                ) : null}
                {mid ? (
                  <button
                    type="button"
                    className="mt-2 text-[11px] text-zinc-600 underline"
                    onClick={() => void loadEvents(mid)}
                  >
                    {expandedId === mid ? t("orchestrator.hide_events") : t("orchestrator.show_events")}
                  </button>
                ) : null}
                {expandedId === mid && eventsByMaster[mid]?.length ? (
                  <ul className="mt-2 space-y-1 rounded-md border border-zinc-100 bg-zinc-50 p-2">
                    {eventsByMaster[mid].map((ev, i) => (
                      <li key={`${ev.created_at}-${i}`} className="text-[10px] text-zinc-700">
                        <span className="text-zinc-400">{ev.created_at}</span> · {ev.type}: {ev.message}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            );
          })}
          {!items.length ? <li className="text-zinc-400">{t("settings.platform.none")}</li> : null}
        </ul>
      </div>
    </div>
  );
}
