import Link from "next/link";

import { ApiError } from "@/components/api-error";
import { JsonCard } from "@/components/json-card";
import { BetaNotice } from "@/components/beta-notice";
import { PageTitle } from "@/components/page-title";
import { apiGet } from "@/lib/api";
import type {
  Agent,
  ExecutionPlan,
  ListResponse,
  Run,
  RunLogLine,
  Task,
  TaskAssignment,
  TaskEvent,
} from "@/lib/octopus-types";

import { TaskDetailClient, type TaskTimelineResponse as TaskTimelineClient } from "./task-detail-client";

type TaskDetailResponse = {
  beta: boolean;
  data: Task;
  assignments: TaskAssignment[];
};

type TaskTimelineResponse = {
  beta: boolean;
  task: Task;
  assignments: TaskAssignment[];
  events: TaskEvent[];
  runs: Run[];
  run_logs: RunLogLine[];
};

type TaskPlanResponse = {
  beta: boolean;
  task: Task;
  plan: ExecutionPlan | null;
};

export default async function TaskDetailPage({
  params,
}: {
  params: Promise<{ taskId: string }>;
}) {
  const { taskId } = await params;

  try {
    const [detail, timeline, agents, plan] = await Promise.all([
      apiGet<TaskDetailResponse>(`/tasks/${encodeURIComponent(taskId)}`),
      apiGet<TaskTimelineResponse>(`/tasks/${encodeURIComponent(taskId)}/timeline`),
      apiGet<ListResponse<Agent>>("/agents"),
      apiGet<TaskPlanResponse>(`/tasks/${encodeURIComponent(taskId)}/plan`),
    ]);

    const task = detail.data;

    return (
      <TaskDetailClient
        taskId={taskId}
        task={task}
        timeline={timeline as unknown as TaskTimelineClient}
        agents={agents.items}
        plan={plan.plan ?? null}
      />
    );
  } catch (error) {
    return (
      <div className="space-y-6 p-6">
        <div className="space-y-1">
          <div className="text-xl font-semibold tracking-tight">Task Detail</div>
          <div className="text-sm text-zinc-600">{`Failed to load task ${taskId}`}</div>
        </div>
        <ApiError error={error} />
      </div>
    );
  }
}
