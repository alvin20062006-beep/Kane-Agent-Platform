"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ProductNotice } from "@/components/product-notice";
import { HandoffCallbackBlock } from "@/components/handoff-callback-block";
import { PageTitle } from "@/components/page-title";
import { apiGet, apiPost, getApiBaseUrl } from "@/lib/api";
import { useT } from "@/lib/i18n/LocaleProvider";
import { listModesFor, type ExecutionMode } from "@/lib/modes";
import { isExternalAgent } from "@/lib/task-completion";
import { useMergedFeed } from "@/lib/use-merged-feed";
import type { Agent, ExecutionPlan, ListResponse, TaskEvent } from "@/lib/octopus-types";

type PlatformSkill = {
  skill_id: string;
  name: string;
  description?: string | null;
};

type TaskTimelineResponse = {
  events: TaskEvent[];
  runs?: Array<{ run_id: string }>;
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
  const [lastRunId, setLastRunId] = useState<string | null>(null);
  const [handoffDir, setHandoffDir] = useState<string | null>(null);
  const [waitingHandoffs, setWaitingHandoffs] = useState(0);
  const [bridgeOnline, setBridgeOnline] = useState(false);
  const [platformSkills, setPlatformSkills] = useState<PlatformSkill[]>([]);
  const { feed, rebuild: rebuildFeed } = useMergedFeed(events, {
    conversationLabel: t("cockpit.feed_conversation"),
  });
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
    const evts = response.events ?? [];
    setEvents(evts);
    const runs = response.runs ?? [];
    setLastRunId(runs.length ? runs[runs.length - 1].run_id : null);
    return evts;
  }, []);

  const refreshHubStatus = useCallback(async () => {
    try {
      const [metrics, bridge] = await Promise.all([
        apiGet<{ fault_recovery?: { waiting_handoffs?: number } }>("/metrics"),
        apiGet<{ data?: { reachable?: boolean; bridge_runtime?: { handoff_dir?: string | null } } }>(
          "/local-bridge"
        ),
      ]);
      setWaitingHandoffs(metrics.fault_recovery?.waiting_handoffs ?? 0);
      setBridgeOnline(!!bridge.data?.reachable);
      setHandoffDir(bridge.data?.bridge_runtime?.handoff_dir ?? null);
    } catch {
      // ignore
    }
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
    refreshHubStatus().catch(() => undefined);
    apiGet<ListResponse<PlatformSkill>>("/skills?limit=12")
      .then((r) => setPlatformSkills(r.items))
      .catch(() => undefined);
    const id = setInterval(() => refreshHubStatus().catch(() => undefined), 5000);
    return () => clearInterval(id);
  }, [refreshAgents, refreshHubStatus]);

  useEffect(() => {
    void rebuildFeed(events);
  }, [events, rebuildFeed]);

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
      const evts = await refreshTimeline(taskId);
      await refreshPlan(taskId);
      await rebuildFeed(evts);
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

  const externalCount = useMemo(() => agents.filter((a) => isExternalAgent(a)).length, [agents]);
  const onlineExternal = useMemo(
    () => agents.filter((a) => isExternalAgent(a) && a.status !== "offline").length,
    [agents]
  );
  const fleetPreview = useMemo(() => {
    const external = agents.filter((a) => isExternalAgent(a));
    const builtin = agents.filter((a) => a.agent_id === "octopus_builtin");
    return [...external, ...builtin].slice(0, 3);
  }, [agents]);
  const dockSkills = useMemo(() => {
    const pinned = ["skill_connect_agent", "skill_handoff_guide"];
    const sorted = [...platformSkills].sort((a, b) => {
      const ai = pinned.indexOf(a.skill_id);
      const bi = pinned.indexOf(b.skill_id);
      if (ai >= 0 && bi >= 0) return ai - bi;
      if (ai >= 0) return -1;
      if (bi >= 0) return 1;
      return a.name.localeCompare(b.name);
    });
    return sorted.slice(0, 6);
  }, [platformSkills]);

  return (
    <div className="space-y-6">
      <PageTitle title={t("cockpit.title")} />

      <ProductNotice note={t("tasks.notice")} />

      <div
        data-testid="cockpit-status-strip"
        className="flex flex-wrap items-center gap-2 rounded-lg border border-zinc-200 bg-white px-3 py-2 text-xs"
      >
        <span className="font-medium text-zinc-700">{t("cockpit.status_strip")}</span>
        <span className={bridgeOnline ? "text-emerald-700" : "text-red-600"}>
          {t("topbar.bridge")}: {bridgeOnline ? "online" : "offline"}
        </span>
        {waitingHandoffs > 0 ? (
          <Link href="/local-bridge" className="text-sky-700 underline">
            {t("cockpit.handoff_waiting").replace("{n}", String(waitingHandoffs))}
          </Link>
        ) : null}
        <span className="text-zinc-500">
          {t("cockpit.fleet_summary")
            .replace("{ext}", String(externalCount))
            .replace("{online}", String(onlineExternal))}
        </span>
        {externalCount === 0 ? (
          <Link
            href="/local-bridge?connect=1"
            className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-emerald-900 hover:bg-emerald-100"
          >
            {t("connect_agent.cockpit_cta")}
          </Link>
        ) : null}
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-12" data-testid="cockpit-five-zone-grid">
        <section className="rounded-lg border border-zinc-200 bg-white p-4 xl:col-span-3" data-testid="cockpit-zone-a">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-zinc-400">
            {t("cockpit.zone_fleet")}
          </div>
          <div className="mt-1 text-sm font-semibold">{t("cockpit.select_operator")}</div>
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
          <div className="mt-4 space-y-2" data-testid="cockpit-fleet-preview">
            {fleetPreview.map((agent) => (
              <div key={agent.agent_id} className="rounded-md border border-zinc-200 px-2 py-1.5 text-xs">
                <div className="font-medium">{agent.display_name}</div>
                <div className="text-zinc-500">
                  {agent.adapter_id ?? agent.type} · {agent.status}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="space-y-3 rounded-lg border border-zinc-200 bg-white p-4 xl:col-span-6" data-testid="cockpit-zone-b">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-zinc-400">
            {t("cockpit.zone_console")}
          </div>
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

        <div className="space-y-4 xl:col-span-3">
          <section className="rounded-lg border border-zinc-200 bg-white p-4" data-testid="cockpit-zone-c">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-zinc-400">
              {t("cockpit.zone_skills")}
            </div>
            <div className="mt-2 space-y-2 text-xs">
              {dockSkills.map((skill) => (
                <div
                  key={skill.skill_id}
                  className={`block rounded-md border px-3 py-2 ${
                    skill.skill_id === "skill_connect_agent"
                      ? "border-emerald-200 bg-emerald-50"
                      : skill.skill_id === "skill_handoff_guide"
                      ? "border-sky-200 bg-sky-50"
                      : "border-zinc-200"
                  }`}
                >
                  <div className="font-medium">{skill.name}</div>
                  {skill.skill_id === "skill_connect_agent" ? (
                    <Link href="/local-bridge?connect=1" className="mt-1 inline-block underline">
                      {t("connect_agent.open")}
                    </Link>
                  ) : null}
                  {skill.description ? (
                    <div className="mt-0.5 text-zinc-500 line-clamp-2">{skill.description}</div>
                  ) : null}
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-lg border border-zinc-200 bg-white p-4" data-testid="cockpit-zone-d">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-zinc-400">
              {t("cockpit.zone_timeline")}
            </div>
            <div className="mt-1 text-sm font-semibold">{t("cockpit.timeline")}</div>
            <div className="mt-3 space-y-2 max-h-[280px] overflow-auto" data-testid="cockpit-merged-feed">
              {feed.length ? (
                feed.map((item) => (
                  <div
                    key={item.id}
                    className={`rounded-md border p-3 text-sm ${
                      item.kind === "conversation" ? "border-violet-200 bg-violet-50/40" : "border-zinc-200"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="font-medium">{item.title}</div>
                      <span className="text-[10px] uppercase text-zinc-400">{item.kind}</span>
                    </div>
                    <div className="mt-1 text-xs text-zinc-500">{item.at}</div>
                    {item.detail ? (
                      <div className="mt-2 text-zinc-700">{item.detail}</div>
                    ) : null}
                  </div>
                ))
              ) : (
                <div className="text-sm text-zinc-500">{t("cockpit.timeline_empty")}</div>
              )}
            </div>
          </section>
        </div>
      </div>

      {pendingApproval && lastTaskId ? (
        <section
          data-testid="cockpit-handoff-pending"
          data-cockpit-zone="e"
          className="rounded-lg border border-amber-200 bg-amber-50 p-4 space-y-3"
        >
          <div className="text-[10px] font-semibold uppercase tracking-wide text-amber-800">
            {t("cockpit.zone_handoff")}
          </div>
          <div className="text-sm font-semibold text-amber-900">
            {t("cockpit.pending_approval")}
          </div>
          <p className="text-xs text-amber-900/90">{t("completion.handoff.desc")}</p>
          <HandoffCallbackBlock
            handoffDir={handoffDir}
            taskId={lastTaskId}
            runId={lastRunId}
          />
          <div className="flex flex-wrap gap-2">
            <Link
              href={`/local-bridge?taskId=${encodeURIComponent(lastTaskId)}`}
              className="rounded-md border border-amber-300 bg-white px-3 py-1.5 text-xs hover:bg-amber-100"
            >
              {t("task_detail.open_bridge")}
            </Link>
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
