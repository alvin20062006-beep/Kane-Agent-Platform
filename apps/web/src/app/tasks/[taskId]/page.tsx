import { ApiError } from "@/components/api-error";
import { apiGet, safeApiGet } from "@/lib/api";
import type {
  AdvisorSuggestion,
  Agent,
  ExecutionPlan,
  ListResponse,
  Run,
  RunLogLine,
  Task,
  TaskAssignment,
  TaskEvent,
  WatchdogEvent,
} from "@/lib/octopus-types";

import { TaskDetailClient, type TaskTimelineResponse as TaskTimelineClient } from "./task-detail-client";

type TaskDetailResponse = {
  version?: string;
  data: Task;
  assignments: TaskAssignment[];
};

type TaskTimelineResponse = {
  version?: string;
  task: Task;
  assignments: TaskAssignment[];
  events: TaskEvent[];
  runs: Run[];
  run_logs: RunLogLine[];
  watchdog_events: WatchdogEvent[];
  orchestrator_context?: import("./task-detail-client").OrchestratorContext | null;
  supervision_summary?: import("./task-detail-client").SupervisionSummary | null;
};

type TaskPlanResponse = {
  version?: string;
  task: Task;
  plan: ExecutionPlan | null;
};

type LocalBridgeBundle = {
  data: {
    bridge_runtime?: {
      handoff_dir?: string | null;
      api_public_url?: string | null;
    };
  };
};

export default async function TaskDetailPage({
  params,
}: {
  params: Promise<{ taskId: string }>;
}) {
  const { taskId } = await params;

  let detail: TaskDetailResponse;
  let timeline: TaskTimelineResponse;
  let agents: ListResponse<Agent>;
  let plan: TaskPlanResponse;
  let advisor: ListResponse<AdvisorSuggestion>;
  let bridgeResult: { data: LocalBridgeBundle | null; error: string | null };
  try {
    [detail, timeline, agents, plan, advisor, bridgeResult] = await Promise.all([
      apiGet<TaskDetailResponse>(`/tasks/${encodeURIComponent(taskId)}`),
      apiGet<TaskTimelineResponse>(`/tasks/${encodeURIComponent(taskId)}/timeline`),
      apiGet<ListResponse<Agent>>("/agents"),
      apiGet<TaskPlanResponse>(`/tasks/${encodeURIComponent(taskId)}/plan`),
      apiGet<ListResponse<AdvisorSuggestion>>(`/advisor/tasks/${encodeURIComponent(taskId)}`),
      safeApiGet<LocalBridgeBundle>("/local-bridge"),
    ]);
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

  const task = detail.data;

  return (
    <TaskDetailClient
      taskId={taskId}
      task={task}
      timeline={timeline as unknown as TaskTimelineClient}
      agents={agents.items}
      plan={plan.plan ?? null}
      advisorSuggestions={advisor.items}
      bridgeRuntime={bridgeResult.data?.data?.bridge_runtime ?? null}
    />
  );
}
