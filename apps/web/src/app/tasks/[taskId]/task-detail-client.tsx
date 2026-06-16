"use client";

import Link from "next/link";
import { useState } from "react";

import { ProductNotice } from "@/components/product-notice";
import { HandoffCallbackBlock } from "@/components/handoff-callback-block";
import { JsonCard } from "@/components/json-card";
import { PageTitle } from "@/components/page-title";
import { getApiBaseUrl } from "@/lib/api";
import { useT } from "@/lib/i18n/LocaleProvider";
import { inferCompletionGuide } from "@/lib/task-completion";
import type {
  AdvisorSuggestion,
  Agent,
  ExecutionPlan,
  Run,
  RunLogLine,
  Task,
  TaskAssignment,
  TaskEvent,
  WatchdogEvent,
} from "@/lib/octopus-types";

import { LiveStream } from "./live-stream";
import { TaskActions, TaskRetryRunButton } from "./task-actions";
import { TaskStatusLive } from "./task-status-live";

export type BridgeRuntimeSnapshot = {
  handoff_dir?: string | null;
  api_public_url?: string | null;
};

export type OrchestratorContext = {
  master_task_id: string;
  subtask_title: string;
  subtask_status: string;
  master_status: string;
  user_instruction: string;
  subtasks_done: number;
  subtasks_total: number;
  master_active: boolean;
};

export type SupervisionSummary = {
  recovery_attempt_count: number;
  watchdog_events_count: number;
  fixer_related_events: number;
  completion_mode_hint: string;
  duration_label: string | null;
  task_status: string;
};

export type TaskTimelineResponse = {
  task: Task;
  assignments: TaskAssignment[];
  events: TaskEvent[];
  runs: Run[];
  run_logs: RunLogLine[];
  watchdog_events: WatchdogEvent[];
  orchestrator_context?: OrchestratorContext | null;
  supervision_summary?: SupervisionSummary | null;
};

export function TaskDetailClient({
  taskId,
  task,
  timeline,
  agents,
  plan,
  advisorSuggestions,
  bridgeRuntime,
}: {
  taskId: string;
  task: Task;
  timeline: TaskTimelineResponse;
  agents: Agent[];
  plan: ExecutionPlan | null;
  advisorSuggestions: AdvisorSuggestion[];
  bridgeRuntime?: BridgeRuntimeSnapshot | null;
}) {
  const t = useT();
  const [currentTask, setCurrentTask] = useState(task);
  const recoveryEvents = timeline.watchdog_events.filter(
    (event) => event.task_id === taskId
  );
  const lastRun =
    timeline.runs.find((r) => r.run_id === currentTask.last_run_id) ??
    timeline.runs[timeline.runs.length - 1];
  const completion = inferCompletionGuide(currentTask, agents, plan, lastRun);
  const showBridgeCta =
    completion.showBridgeLink ||
    completion.mode === "handoff_callback" ||
    completion.mode === "bridge_sync";
  const bridgeHref = showBridgeCta
    ? `/local-bridge?taskId=${encodeURIComponent(taskId)}`
    : "/local-bridge";
  const apiBase = bridgeRuntime?.api_public_url ?? getApiBaseUrl();
  const showHandoffDetails =
    completion.mode === "handoff_callback" || completion.showBridgeLink;
  const orch = timeline.orchestrator_context;
  const supervision = timeline.supervision_summary;

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between gap-3">
        <PageTitle title={t("task_detail.title")} subtitle={t("task_detail.subtitle", taskId)} />
        <Link
          href="/tasks"
          className="rounded-md border border-zinc-200 px-3 py-2 text-sm hover:bg-zinc-50"
        >
          {t("task_detail.back")}
        </Link>
      </div>

      <ProductNotice note={t("task_detail.notice")} />

      {orch ? (
        <section
          data-testid="task-batch-context"
          className="rounded-lg border border-violet-200 bg-violet-50 px-4 py-3 text-sm text-violet-950"
        >
          <div className="font-semibold">{t("task_detail.batch_context_title")}</div>
          <p className="mt-1 text-xs">
            {t("task_detail.batch_context_desc")
              .replace("{title}", orch.subtask_title)
              .replace("{done}", String(orch.subtasks_done))
              .replace("{total}", String(orch.subtasks_total))}
          </p>
          <Link
            href={`/orchestrator?master=${encodeURIComponent(orch.master_task_id)}`}
            className="mt-2 inline-block text-xs font-medium underline"
          >
            {t("task_detail.open_batch")} · {orch.master_task_id}
          </Link>
        </section>
      ) : null}

      {currentTask.needs_attention ? (
        <div
          data-testid="task-attention-banner"
          className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950"
        >
          <div className="font-semibold">{t("task_detail.attention_banner")}</div>
          {currentTask.attention_reason ? (
            <div className="mt-1 text-xs">{currentTask.attention_reason}</div>
          ) : null}
          <div className="mt-3 flex flex-wrap gap-2">
            <TaskRetryRunButton
              taskId={taskId}
              testId="attention-retry-run-button"
              className="rounded-md border border-emerald-600 bg-emerald-600 px-3 py-1.5 text-xs text-white hover:bg-emerald-700 disabled:opacity-50"
            />
            <Link
              href="/watchdog"
              className="rounded-md border border-amber-300 bg-white px-3 py-1.5 text-xs hover:bg-amber-100"
            >
              {t("task_detail.open_watchdog")}
            </Link>
            {showBridgeCta ? (
              <Link
                href={bridgeHref}
                className="rounded-md border border-amber-300 bg-white px-3 py-1.5 text-xs hover:bg-amber-100"
              >
                {t("task_detail.open_bridge")}
              </Link>
            ) : null}
          </div>
        </div>
      ) : null}

      <section
        data-testid="task-completion-card"
        className="rounded-lg border border-zinc-200 bg-white p-4"
      >
        <div className="text-sm font-semibold">{t("completion.title")}</div>
        <div className="mt-2 text-sm font-medium text-zinc-800">{t(completion.titleKey)}</div>
        <p className="mt-1 text-sm text-zinc-600">{t(completion.descKey)}</p>
        <p className="mt-2 rounded-md bg-zinc-50 px-3 py-2 text-xs text-zinc-700">{t(completion.nextKey)}</p>
        {completion.showBridgeLink ? (
          <Link href={bridgeHref} className="mt-2 inline-block text-xs text-sky-700 underline">
            {t("task_detail.open_bridge")}
          </Link>
        ) : null}
        {showHandoffDetails ? (
          <div className="mt-3">
            <HandoffCallbackBlock
            testId="task-handoff-details"
            handoffDir={bridgeRuntime?.handoff_dir}
            apiBase={apiBase}
            taskId={taskId}
            runId={lastRun?.run_id}
          />
          </div>
        ) : null}
      </section>

      <TaskActions
        taskId={taskId}
        agents={agents}
        currentAgentId={task.assigned_agent_id}
        taskStatus={task.status}
        executionMode={task.execution_mode}
        pendingApprovalId={timeline.task.pending_approval_id ?? null}
      />

      <section className="grid gap-4 lg:grid-cols-3">
        <div data-testid="task-summary-card" className="rounded-lg border border-zinc-200 bg-white p-4 lg:col-span-2">
          <div className="text-sm font-semibold">{task.title}</div>
          <div className="mt-2 text-sm text-zinc-700">
            {task.description || t("task_detail.no_description")}
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 text-sm">
            <div>
              <div className="text-xs text-zinc-500">{t("task_detail.assigned_agent")}</div>
              <div className="mt-1">{task.assigned_agent_id ?? t("task_detail.unassigned")}</div>
            </div>
            <div>
              <div className="text-xs text-zinc-500">{t("task_detail.created")}</div>
              <div className="mt-1">{task.created_at}</div>
            </div>
            <div>
              <div className="text-xs text-zinc-500">{t("task_detail.updated")}</div>
              <div className="mt-1">{task.updated_at ?? task.created_at}</div>
            </div>
            <div>
              <div className="text-xs text-zinc-500">{t("task_detail.retry_count")}</div>
              <div className="mt-1">{task.retry_count}</div>
            </div>
            <div>
              <div className="text-xs text-zinc-500">Queue priority</div>
              <div className="mt-1">{task.queue_priority}</div>
            </div>
            <div>
              <div className="text-xs text-zinc-500">Correlation</div>
              <div className="mt-1 break-all font-mono text-xs">
                {task.correlation_id ?? "Not assigned yet"}
              </div>
            </div>
            <div>
              <div className="text-xs text-zinc-500">Source task</div>
              <div className="mt-1 break-all font-mono text-xs">
                {currentTask.source_task_id ?? "None"}
              </div>
            </div>
            <TaskStatusLive taskId={taskId} initialTask={task} onTaskChange={setCurrentTask} />
          </div>
        </div>

        <div data-testid="task-result-card" className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-sm font-semibold">{t("task_detail.result")}</div>
          <div className="mt-2 text-sm text-zinc-700 whitespace-pre-wrap">
            {t("task_detail.result_hint")}
          </div>
          <div className="mt-4 text-xs text-zinc-500">{t("task_detail.result_payload")}</div>
          <div className="mt-2">
            <JsonCard data={task.result_payload ?? { pending: true }} />
          </div>
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-sm font-semibold">{t("task_detail.assignment_history")}</div>
          <div className="mt-3 space-y-2">
            {timeline.assignments.length ? (
              timeline.assignments.map((assignment) => (
                <div key={assignment.assignment_id} className="rounded-md border border-zinc-200 p-3 text-sm">
                  <div className="font-medium">{assignment.agent_id}</div>
                  <div className="mt-1 text-xs text-zinc-500">
                    {assignment.assigned_at} • {t("task_detail.assigned_by")} {assignment.assigned_by}
                  </div>
                  {assignment.note ? <div className="mt-2 text-zinc-700">{assignment.note}</div> : null}
                </div>
              ))
            ) : (
              <div className="text-sm text-zinc-500">{t("task_detail.no_assignments")}</div>
            )}
          </div>
        </div>

        <div data-testid="task-timeline-card" className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-sm font-semibold">{t("task_detail.timeline_events")}</div>
          <div className="mt-3 space-y-2">
            {timeline.events.length ? (
              timeline.events.map((event) => (
                <div
                  data-testid={`timeline-event-${event.type}`}
                  key={event.event_id}
                  className="rounded-md border border-zinc-200 p-3 text-sm"
                >
                  <div className="font-medium">{event.type}</div>
                  <div className="mt-1 text-xs text-zinc-500">{event.created_at}</div>
                  {event.message ? <div className="mt-2 text-zinc-700">{event.message}</div> : null}
                  {event.payload ? (
                    <div className="mt-2">
                      <JsonCard data={event.payload} />
                    </div>
                  ) : null}
                </div>
              ))
            ) : (
              <div className="text-sm text-zinc-500">{t("task_detail.no_events")}</div>
            )}
          </div>
        </div>
      </section>

      <section data-testid="task-recovery-history-card" className="rounded-lg border border-zinc-200 bg-white p-4">
        <div className="text-sm font-semibold">{t("task_detail.recovery_history_title")}</div>
        <div className="mt-2 text-sm text-zinc-600">{t("task_detail.recovery_history_desc")}</div>
        <div className="mt-4 grid gap-3 md:grid-cols-2 text-sm">
          <div className="rounded-md border border-zinc-200 p-3">
            <div className="text-xs text-zinc-500">{t("task_detail.needs_attention_label")}</div>
            <div data-testid="task-attention-state" className="mt-1 font-medium">
              {currentTask.needs_attention ? t("common.yes") : t("common.no")}
            </div>
            <div className="mt-2 text-xs text-zinc-500">{t("task_detail.attention_reason_label")}</div>
            <div className="mt-1 text-zinc-700">{currentTask.attention_reason ?? t("dashboard.none")}</div>
          </div>
          <div className="rounded-md border border-zinc-200 p-3">
            <div className="text-xs text-zinc-500">{t("task_detail.recovery_auto_count")}</div>
            <div className="mt-1 font-medium">
              {currentTask.recovery_attempt_count} / {currentTask.max_recovery_attempts}
            </div>
            <div className="mt-2 text-xs text-zinc-500">{t("task_detail.recovery_manual_count")}</div>
            <div className="mt-1 font-medium">{currentTask.retry_count}</div>
          </div>
        </div>
        <div className="mt-4 space-y-3">
          {recoveryEvents.length ? (
            recoveryEvents.map((event) => (
              <div key={event.event_id} className="rounded-md border border-zinc-200 p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="font-medium">{event.type}</div>
                  <div className="text-xs text-zinc-500">
                    {event.source ?? "watchdog"} / {event.issue_status ?? "open"}
                  </div>
                </div>
                <div className="mt-1 text-xs text-zinc-500">{event.created_at}</div>
                {event.message ? <div className="mt-2 text-zinc-700">{event.message}</div> : null}
                <div className="mt-2 grid gap-2 md:grid-cols-2">
                  <div>
                    <div className="text-xs text-zinc-500">{t("task_detail.issue_class")}</div>
                    <div className="mt-1">{event.issue_class ?? t("dashboard.none")}</div>
                  </div>
                  <div>
                    <div className="text-xs text-zinc-500">{t("task_detail.suggested_action")}</div>
                    <div className="mt-1">{event.suggested_action ?? t("dashboard.none")}</div>
                  </div>
                </div>
                {event.recovery_hint ? (
                  <div className="mt-2 rounded-md bg-zinc-50 p-2 text-xs text-zinc-700">
                    {event.recovery_hint}
                  </div>
                ) : null}
              </div>
            ))
          ) : (
            <div className="text-sm text-zinc-500">{t("task_detail.recovery_none")}</div>
          )}
        </div>
      </section>

      <section data-testid="task-advisor-card" className="rounded-lg border border-zinc-200 bg-white p-4">
        <div className="text-sm font-semibold">{t("task_detail.advisor_notes_title")}</div>
        <div className="mt-2 text-sm text-zinc-600">
          {t("task_detail.advisor_notes_desc")}
        </div>
        <div className="mt-4 space-y-3">
          {advisorSuggestions.length ? (
            advisorSuggestions.map((suggestion) => (
              <div key={suggestion.suggestion_id} className="rounded-md border border-zinc-200 p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="font-medium">{suggestion.title}</div>
                  <div className="text-xs text-zinc-500">
                    {suggestion.severity} / {suggestion.status} / confidence={suggestion.confidence ?? "low"}
                  </div>
                </div>
                <div className="mt-2 text-zinc-700">{suggestion.summary}</div>
                <div className="mt-2 flex flex-wrap gap-2 text-xs text-zinc-500">
                  <span className="rounded-full border border-zinc-200 px-2 py-1">
                    occurrences={suggestion.occurrence_count ?? 1}
                  </span>
                  <span className="rounded-full border border-zinc-200 px-2 py-1">
                    affected_targets={suggestion.affected_targets ?? 1}
                  </span>
                </div>
                <div className="mt-2 text-xs text-zinc-500">{suggestion.rationale}</div>
                <div className="mt-2 rounded-md bg-zinc-50 p-2 text-xs text-zinc-700">
                  next: {suggestion.recommended_action}
                </div>
              </div>
            ))
          ) : (
            <div className="text-sm text-zinc-500">No advisor notes have been generated for this task yet.</div>
          )}
        </div>
      </section>

      {plan ? (
        <section className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-sm font-semibold">{t("task_detail.track_plan")}</div>
          <div className="mt-3 space-y-2">
            {plan.steps.map((step) => (
              <div key={step.step_id} className="rounded-md border border-zinc-200 p-3 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-medium">{step.kind}</div>
                  <div className="text-xs text-zinc-500">{step.status}</div>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section data-testid="task-runs-card" className="rounded-lg border border-zinc-200 bg-white p-4">
        <div className="text-sm font-semibold">{t("task_detail.runs_logs")}</div>
        <div className="mt-3 space-y-4">
          {timeline.runs.length ? (
            timeline.runs.map((run) => {
              const logs = timeline.run_logs.filter((item) => item.run_id === run.run_id);
              const activityLabel = run.started_at ? "Started" : "Queued";
              const activityAt = run.started_at ?? run.queued_at ?? t("dashboard.none");
              return (
                <div key={run.run_id} className="rounded-lg border border-zinc-200 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="font-medium">
                        {run.run_id} • {run.status}
                      </div>
                      <div className="mt-1 text-xs text-zinc-500">
                        {run.integration_path ?? t("dashboard.unknown_path")} • {activityLabel}: {activityAt}
                      </div>
                    </div>
                    <div className="text-xs text-zinc-500">
                      {t("task_detail.finished")}: {run.finished_at ?? t("dashboard.none")}
                    </div>
                  </div>
                  <div className="mt-2 text-xs text-zinc-500">parent_run_id: {run.parent_run_id ?? "None"}</div>
                  {run.error ? <div className="mt-3 text-sm text-rose-700">{run.error}</div> : null}
                  <div className="mt-3 grid gap-3 xl:grid-cols-2">
                    <div>
                      <div className="text-xs font-medium text-zinc-600">Input snapshot</div>
                      <div className="mt-2">
                        <JsonCard data={run.input_snapshot ?? { pending: true }} />
                      </div>
                    </div>
                    <div>
                      <div className="text-xs font-medium text-zinc-600">Output snapshot</div>
                      <div className="mt-2">
                        <JsonCard data={run.output_snapshot ?? { pending: true }} />
                      </div>
                    </div>
                    <div>
                      <div className="text-xs font-medium text-zinc-600">Environment summary</div>
                      <div className="mt-2">
                        <JsonCard data={run.environment_summary ?? { pending: true }} />
                      </div>
                    </div>
                    <div>
                      <div className="text-xs font-medium text-zinc-600">Callback summary</div>
                      <div className="mt-2">
                        <JsonCard data={run.callback_summary ?? { pending: false }} />
                      </div>
                    </div>
                  </div>

                  {logs.length ? (
                    <div className="mt-3 rounded-md border border-zinc-200 bg-zinc-50 p-3">
                      <div className="text-xs font-medium text-zinc-600">{t("task_detail.run_logs")}</div>
                      <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap text-[11px] text-zinc-700">
                        {logs.map((l) => l.message).join("\n")}
                      </pre>
                    </div>
                  ) : null}
                </div>
              );
            })
          ) : (
            <div className="text-sm text-zinc-500">{t("task_detail.no_runs")}</div>
          )}
        </div>
      </section>

      {supervision ? (
        <section
          data-testid="task-supervision-summary"
          className="rounded-lg border border-zinc-200 bg-white p-4"
        >
          <div className="text-sm font-semibold">{t("task_detail.supervision_summary_title")}</div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4 text-sm">
            <div>
              <div className="text-xs text-zinc-500">{t("task_detail.supervision_duration")}</div>
              <div className="mt-1">{supervision.duration_label ?? t("dashboard.none")}</div>
            </div>
            <div>
              <div className="text-xs text-zinc-500">{t("task_detail.supervision_completion")}</div>
              <div className="mt-1">{supervision.completion_mode_hint}</div>
            </div>
            <div>
              <div className="text-xs text-zinc-500">{t("task_detail.supervision_recovery")}</div>
              <div className="mt-1">{supervision.recovery_attempt_count}</div>
            </div>
            <div>
              <div className="text-xs text-zinc-500">{t("task_detail.supervision_fixer")}</div>
              <div className="mt-1">{supervision.fixer_related_events}</div>
            </div>
          </div>
        </section>
      ) : null}

      <LiveStream taskId={taskId} lastRunId={timeline.task.last_run_id} />
    </div>
  );
}

