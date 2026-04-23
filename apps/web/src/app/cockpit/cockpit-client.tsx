"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { BetaNotice } from "@/components/beta-notice";
import { PageTitle } from "@/components/page-title";
import { apiGet, apiPost, getApiBaseUrl } from "@/lib/api";
import { useT } from "@/lib/i18n/LocaleProvider";
import { listModesFor, type ExecutionMode } from "@/lib/modes";
import type { Agent, ExecutionPlan, ListResponse, TaskEvent } from "@/lib/octopus-types";

type TaskTimelineResponse = {
  events: TaskEvent[];
};

type TaskPlanResponse = {
  task: { execution_plan_id?: string | null; pending_approval_id?: string | null };
  plan: ExecutionPlan | null;
};

export function CockpitClient() {
  const t = useT();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentId, setAgentId] = useState("octopus_builtin");
  const [mode, setMode] = useState<ExecutionMode>("commander");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [lastTaskId, setLastTaskId] = useState<string | null>(null);
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [resultText, setResultText] = useState("");
  const [pendingApproval, setPendingApproval] = useState<string | null>(null);
  const [plan, setPlan] = useState<ExecutionPlan | null>(null);
  const sseUrl = useMemo(() => {
    if (!lastTaskId) return null;
    return `${getApiBaseUrl()}/tasks/${encodeURIComponent(lastTaskId)}/events/stream`;
  }, [lastTaskId]);

  const refreshAgents = useCallback(async () => {
    const response = await apiGet<ListResponse<Agent>>("/agents");
    setAgents(response.items);
  }, []);

  const refreshTimeline = useCallback(async (taskId: string) => {
    const response = await apiGet<TaskTimelineResponse>(
      `/tasks/${encodeURIComponent(taskId)}/timeline`
    );
    setEvents(response.events ?? []);
  }, []);

  const refreshPlan = useCallback(async (taskId: string) => {
    const response = await apiGet<TaskPlanResponse>(
      `/tasks/${encodeURIComponent(taskId)}/plan`
    );
    setPendingApproval(response.task?.pending_approval_id ?? null);
    setPlan(response.plan ?? null);
  }, []);

  useEffect(() => {
    refreshAgents().catch(() => undefined);
  }, [refreshAgents]);

  // PRD §5: Commander / Pilot 仅在选中 Kanaloa 时可用；切到外部 Agent 自动切 Direct Agent
  const isOctopusAgent = agentId === "octopus_builtin";
  useEffect(() => {
    if (!isOctopusAgent && mode !== "direct_agent") {
      setMode("direct_agent");
    }
  }, [isOctopusAgent, mode]);

  useEffect(() => {
    if (!sseUrl) return;
    const es = new EventSource(sseUrl);
    es.addEventListener("task_event", (evt) => {
      try {
        const data = JSON.parse((evt as MessageEvent).data);
        setEvents((prev) => {
          if (prev.some((e) => e.event_id === data.event_id)) return prev;
          return [...prev, data].slice(-200);
        });
      } catch {
        // ignore
      }
    });
    es.onerror = () => {
      // leave it; browser will retry
    };
    return () => es.close();
  }, [sseUrl]);

  const onCreateAssignRun = async () => {
    setBusy(true);
    setResultText("");
    setPendingApproval(null);
    setPlan(null);
    try {
      const created = await apiPost<{ data: { task_id: string } }>("/tasks", {
        title: title.trim() || "Untitled cockpit task",
        description: description.trim() || null,
        execution_mode: mode,
      });
      const taskId = created.data.task_id;
      setLastTaskId(taskId);
      await apiPost(`/tasks/${encodeURIComponent(taskId)}/assign`, {
        agent_id: agentId,
      });
      const run = await apiPost<Record<string, unknown>>(
        `/tasks/${encodeURIComponent(taskId)}/run`
      );
      setResultText(JSON.stringify(run, null, 2));
      await refreshTimeline(taskId);
      await refreshPlan(taskId);
    } catch (error) {
      setResultText(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  const onApprove = async () => {
    if (!lastTaskId) return;
    setBusy(true);
    try {
      const res = await apiPost(`/tasks/${encodeURIComponent(lastTaskId)}/approve`, { note: "approved_from_cockpit" });
      setResultText(JSON.stringify(res, null, 2));
      await refreshTimeline(lastTaskId);
      await refreshPlan(lastTaskId);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageTitle title={t("cockpit.title")} />

      <BetaNotice note={t("tasks.beta_notice")} />

      <div className="text-xs text-zinc-500">
        API base: <span className="font-mono">{getApiBaseUrl()}</span>
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-12">
        <section className="rounded-lg border border-zinc-200 bg-white p-4 xl:col-span-3">
          <div className="text-sm font-semibold">{t("cockpit.select_operator")}</div>
          <select
            className="mt-2 w-full rounded-md border border-zinc-200 px-3 py-2 text-sm"
            value={agentId}
            onChange={(event) => setAgentId(event.target.value)}
          >
            {agents.map((agent) => (
              <option key={agent.agent_id} value={agent.agent_id}>
                {agent.display_name} ({agent.adapter_id ?? agent.type})
              </option>
            ))}
          </select>
          <button
            type="button"
            className="mt-3 text-xs text-zinc-600 underline"
            onClick={() => refreshAgents()}
          >
            {t("common.retry")}
          </button>
        </section>

        <section className="space-y-3 rounded-lg border border-zinc-200 bg-white p-4 xl:col-span-6">
          <div className="flex items-center justify-between">
            <div className="text-sm font-semibold">{t("mode.exec_label")}</div>
            {!isOctopusAgent && (
              <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] text-zinc-500">
                {t("mode.kanaloa_only_hint")}
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {listModesFor(isOctopusAgent).map((item) => {
              const disabled = item.kanaloaOnly && !isOctopusAgent;
              const active = mode === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  disabled={disabled}
                  onClick={() => setMode(item.id)}
                  title={disabled ? t("mode.kanaloa_only_hint") : t(item.labelKey)}
                  className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                    active
                      ? "border-[var(--octo-royal-blue)] bg-[var(--octo-royal-blue)] text-white"
                      : disabled
                      ? "border-zinc-100 bg-zinc-50 text-zinc-400 cursor-not-allowed"
                      : "border-zinc-200 text-zinc-700 hover:border-[var(--octo-royal-blue)] hover:text-[var(--octo-royal-blue)]"
                  }`}
                >
                  {t(item.labelKey)}
                </button>
              );
            })}
          </div>
          <div>
            <div className="mb-1 text-xs text-zinc-600">{t("cockpit.target_label")}</div>
            <input
              className="w-full rounded-md border border-zinc-200 px-3 py-2 text-sm"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder={t("cockpit.target_placeholder")}
            />
          </div>
          <div>
            <div className="mb-1 text-xs text-zinc-600">
              {t("cockpit.context_label")}
            </div>
            <textarea
              className="min-h-[140px] w-full rounded-md border border-zinc-200 px-3 py-2 text-sm"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder={t("cockpit.context_placeholder")}
            />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={busy}
              onClick={onCreateAssignRun}
              className="rounded-md bg-[var(--octo-royal-blue)] px-4 py-2 text-sm text-white disabled:opacity-50"
            >
              {busy ? t("cockpit.dispatching") : t("cockpit.dispatch")}
            </button>
            {lastTaskId ? (
              <Link
                href={`/tasks/${encodeURIComponent(lastTaskId)}`}
                className="text-sm text-zinc-700 underline"
              >
                {t("action.open_task")}
              </Link>
            ) : null}
          </div>
        </section>

        <section className="rounded-lg border border-zinc-200 bg-white p-4 xl:col-span-3">
          <div className="text-sm font-semibold">{t("cockpit.timeline")}</div>
          <div className="mt-3 space-y-2 max-h-[420px] overflow-auto">
            {events.length ? (
              events.map((event) => (
                <div
                  key={event.event_id}
                  className="rounded-md border border-zinc-200 p-3 text-sm"
                >
                  <div className="font-medium">{event.type}</div>
                  <div className="mt-1 text-xs text-zinc-500">{event.created_at}</div>
                  {event.message ? (
                    <div className="mt-2 text-zinc-700">{event.message}</div>
                  ) : null}
                </div>
              ))
            ) : (
              <div className="text-sm text-zinc-500">{t("cockpit.timeline_empty")}</div>
            )}
          </div>
        </section>
      </div>

      {pendingApproval && lastTaskId ? (
        <section className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <div className="text-sm font-semibold text-amber-900">
            {t("cockpit.pending_approval")}
          </div>
          <div className="mt-1 text-xs font-mono text-amber-900/80">{pendingApproval}</div>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={onApprove}
              className="rounded-md bg-amber-900 px-4 py-2 text-sm text-white disabled:opacity-50"
            >
              {t("cockpit.approve_continue")}
            </button>
          </div>
        </section>
      ) : null}

      {plan ? (
        <section className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-sm font-semibold">{t("cockpit.pilot_plan")}</div>
          <div className="mt-3 space-y-2">
            {plan.steps.map((s) => (
              <div key={s.step_id} className="rounded-md border border-zinc-200 p-3 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-medium">{s.kind}</div>
                  <div className="text-xs text-zinc-500">{s.status}</div>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section className="rounded-lg border border-zinc-200 bg-white p-4">
        <div className="text-sm font-semibold">{t("cockpit.api_response")}</div>
        <pre className="mt-3 max-h-[320px] overflow-auto whitespace-pre-wrap rounded-md bg-zinc-950 p-3 text-xs text-zinc-100">
          {resultText || t("cockpit.api_response_empty")}
        </pre>
      </section>
    </div>
  );
}
