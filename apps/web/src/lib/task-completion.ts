import type { Agent, ExecutionPlan, Run, Task } from "./octopus-types";

export type CompletionMode =
  | "builtin_auto"
  | "bridge_sync"
  | "handoff_callback"
  | "policy_approve"
  | "pilot_steps"
  | "unknown";

export type CompletionGuide = {
  mode: CompletionMode;
  titleKey: string;
  descKey: string;
  nextKey: string;
  showBridgeLink?: boolean;
  showApprove?: boolean;
};

function integrationPath(run: Run | null | undefined): string {
  return (run?.integration_path ?? "").toLowerCase();
}

export function inferCompletionGuide(
  task: Task,
  agents: Agent[],
  plan: ExecutionPlan | null,
  lastRun: Run | null | undefined,
): CompletionGuide {
  if (plan && task.execution_mode === "pilot") {
    return {
      mode: "pilot_steps",
      titleKey: "completion.pilot.title",
      descKey: "completion.pilot.desc",
      nextKey: "completion.pilot.next",
      showApprove: Boolean(task.pending_approval_id),
    };
  }

  if (task.status === "waiting_approval") {
    const path = integrationPath(lastRun);
    if (path.includes("handoff") || path.includes("manual") || path.includes("cursor")) {
      return {
        mode: "handoff_callback",
        titleKey: "completion.handoff.title",
        descKey: "completion.handoff.desc",
        nextKey: "completion.handoff.next",
        showBridgeLink: true,
      };
    }
    return {
      mode: "policy_approve",
      titleKey: "completion.approve.title",
      descKey: "completion.approve.desc",
      nextKey: "completion.approve.next",
      showApprove: true,
    };
  }

  const agent = agents.find((a) => a.agent_id === task.assigned_agent_id);
  if (agent?.type === "builtin" || agent?.adapter_id === "builtin_octopus") {
    return {
      mode: "builtin_auto",
      titleKey: "completion.builtin.title",
      descKey: "completion.builtin.desc",
      nextKey: "completion.builtin.next",
    };
  }

  const path = integrationPath(lastRun);
  if (path.includes("handoff") || path.includes("manual")) {
    return {
      mode: "handoff_callback",
      titleKey: "completion.handoff.title",
      descKey: "completion.handoff.desc",
      nextKey: "completion.handoff.next",
      showBridgeLink: true,
    };
  }

  if (agent?.type === "external") {
    return {
      mode: "bridge_sync",
      titleKey: "completion.bridge.title",
      descKey: "completion.bridge.desc",
      nextKey: "completion.bridge.next",
      showBridgeLink: true,
    };
  }

  return {
    mode: "unknown",
    titleKey: "completion.unknown.title",
    descKey: "completion.unknown.desc",
    nextKey: "completion.unknown.next",
  };
}

export function isExternalAgent(agent: Agent | undefined): boolean {
  if (!agent) return false;
  if (agent.type === "external") return true;
  const id = agent.adapter_id ?? "";
  return id.length > 0 && id !== "builtin_octopus";
}

const SUBTASK_TERMINAL = new Set(["completed", "failed", "skipped", "cancelled", "succeeded"]);

export function subtaskProgress(subtasks: Array<{ status?: string }>): {
  done: number;
  total: number;
  pct: number;
} {
  const total = subtasks.length;
  const done = subtasks.filter((s) =>
    SUBTASK_TERMINAL.has((s.status ?? "").toLowerCase()),
  ).length;
  return { done, total, pct: total ? Math.round((done / total) * 100) : 0 };
}

export function masterIsActive(status: string | undefined): boolean {
  const s = (status ?? "").toLowerCase();
  return s.length > 0 && !["completed", "failed", "cancelled"].includes(s);
}
