"use client";

import Link from "next/link";

import { BetaNotice } from "@/components/beta-notice";
import { JsonCard } from "@/components/json-card";
import { PageTitle } from "@/components/page-title";
import { useT } from "@/lib/i18n/LocaleProvider";
import type {
  Agent,
  ExecutionPlan,
  Run,
  RunLogLine,
  Task,
  TaskAssignment,
  TaskEvent,
} from "@/lib/octopus-types";

import { LiveStream } from "./live-stream";
import { TaskActions } from "./task-actions";
import { TaskStatusLive } from "./task-status-live";

export type TaskTimelineResponse = {
  task: Task;
  assignments: TaskAssignment[];
  events: TaskEvent[];
  runs: Run[];
  run_logs: RunLogLine[];
};

export function TaskDetailClient({
  taskId,
  task,
  timeline,
  agents,
  plan,
}: {
  taskId: string;
  task: Task;
  timeline: TaskTimelineResponse;
  agents: Agent[];
  plan: ExecutionPlan | null;
}) {
  const t = useT();

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

      <BetaNotice note={t("task_detail.beta_notice")} />

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
            <TaskStatusLive taskId={taskId} initialTask={task} />
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
              return (
                <div key={run.run_id} className="rounded-lg border border-zinc-200 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="font-medium">
                        {run.run_id} • {run.status}
                      </div>
                      <div className="mt-1 text-xs text-zinc-500">
                        {run.integration_path ?? t("dashboard.unknown_path")} • {run.started_at ?? t("dashboard.none")}
                      </div>
                    </div>
                    <div className="text-xs text-zinc-500">
                      {t("task_detail.finished")}: {run.finished_at ?? t("dashboard.none")}
                    </div>
                  </div>
                  {run.error ? <div className="mt-3 text-sm text-rose-700">{run.error}</div> : null}

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

      <LiveStream taskId={taskId} />
    </div>
  );
}

