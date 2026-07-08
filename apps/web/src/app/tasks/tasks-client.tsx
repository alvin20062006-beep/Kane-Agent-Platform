"use client";

import Link from "next/link";
import { useState } from "react";

import { apiPost } from "@/lib/api";
import { useT } from "@/lib/i18n/LocaleProvider";
import { listModesFor, type ExecutionMode } from "@/lib/modes";
import type { Agent, Task } from "@/lib/octopus-types";

type Props = {
  initialTasks: Task[];
  agents: Agent[];
  totalTasks?: number;
};

type CreateFeedback =
  | { kind: "success"; task: Task }
  | { kind: "error"; message: string };

export function TasksClient({ initialTasks, agents, totalTasks }: Props) {
  const t = useT();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [queuePriority, setQueuePriority] = useState<Task["queue_priority"]>("normal");
  const [executionMode, setExecutionMode] = useState<ExecutionMode>("commander");
  const [busy, setBusy] = useState(false);
  const [createFeedback, setCreateFeedback] = useState<CreateFeedback | null>(null);
  const [tasks, setTasks] = useState(initialTasks);

  const createTask = async () => {
    setBusy(true);
    setCreateFeedback(null);
    try {
      const response = await apiPost<{ data: Task }>("/tasks", {
        title: title.trim() || t("tasks.untitled_default"),
        description: description.trim() || null,
        execution_mode: executionMode,
        queue_priority: queuePriority,
      });
      setTasks([response.data, ...tasks]);
      setCreateFeedback({ kind: "success", task: response.data });
      setTitle("");
      setDescription("");
    } catch (error) {
      setCreateFeedback({ kind: "error", message: error instanceof Error ? error.message : String(error) });
    } finally {
      setBusy(false);
    }
  };

  const modes = listModesFor(true);

  return (
    <div className="space-y-6">
      <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-900">
        <span className="font-semibold">{t("common.version")}</span>
        <span className="mx-2">/</span>
        <span>{t("tasks.notice")}</span>
      </div>

      <section className="grid gap-4 xl:grid-cols-[1.1fr_1.9fr]">
        <div className="rounded-lg border border-zinc-200 bg-white p-4 space-y-3">
          <div className="text-sm font-semibold">{t("tasks.new_task")}</div>
          <div>
            <div className="mb-1 text-xs text-zinc-600">{t("tasks.title_label")}</div>
            <input
              data-testid="task-title-input"
              className="w-full rounded-md border border-zinc-200 px-3 py-2 text-sm"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder={t("tasks.title_placeholder")}
            />
          </div>
          <div>
            <div className="mb-1 text-xs text-zinc-600">{t("tasks.description_label")}</div>
            <textarea
              data-testid="task-description-input"
              className="min-h-[120px] w-full rounded-md border border-zinc-200 px-3 py-2 text-sm"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder={t("tasks.description_placeholder")}
            />
          </div>
          <div>
            <div className="mb-1 text-xs text-zinc-600">{t("tasks.exec_mode_label")}</div>
            <div className="flex flex-wrap gap-2">
              {modes.map((m) => (
                <button
                  data-testid={`execution-mode-${m.id}`}
                  key={m.id}
                  type="button"
                  onClick={() => setExecutionMode(m.id)}
                  className={`rounded-full border px-3 py-1 text-xs ${
                    executionMode === m.id
                      ? "border-zinc-900 bg-zinc-900 text-white"
                      : "border-zinc-200 hover:border-zinc-400"
                  }`}
                >
                  {t(m.labelKey)}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="mb-1 text-xs text-zinc-600">Queue priority</div>
            <select
              data-testid="task-priority-select"
              className="w-full rounded-md border border-zinc-200 px-3 py-2 text-sm"
              value={queuePriority}
              onChange={(event) => setQueuePriority(event.target.value as Task["queue_priority"])}
            >
              <option value="low">low</option>
              <option value="normal">normal</option>
              <option value="high">high</option>
              <option value="urgent">urgent</option>
            </select>
          </div>
          <button
            data-testid="create-task-button"
            type="button"
            disabled={busy}
            onClick={createTask}
            className="rounded-md bg-zinc-900 px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            {busy ? t("tasks.creating") : t("tasks.create")}
          </button>
          {createFeedback ? (
            <div
              data-testid="task-create-response"
              className={`rounded-md border px-3 py-3 text-xs ${
                createFeedback.kind === "success"
                  ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                  : "border-rose-200 bg-rose-50 text-rose-800"
              }`}
            >
              {createFeedback.kind === "success" ? (
                <div data-testid="task-create-success" className="space-y-2">
                  <div className="font-semibold">{t("tasks.create_success")}</div>
                  <div className="text-zinc-700">
                    {createFeedback.task.title} / {createFeedback.task.status}
                  </div>
                  <div className="font-mono text-[11px] text-zinc-600">{createFeedback.task.task_id}</div>
                  <div className="flex flex-wrap gap-2 pt-1">
                    <Link
                      data-testid="task-create-detail-link"
                      href={`/tasks/${encodeURIComponent(createFeedback.task.task_id)}`}
                      className="rounded-md border border-emerald-300 bg-white px-2 py-1 font-medium text-emerald-800 hover:border-emerald-500"
                    >
                      {t("tasks.view_details")}
                    </Link>
                    {createFeedback.task.last_run_id ? (
                      <Link
                        data-testid="task-create-run-link"
                        href={`/tasks/${encodeURIComponent(createFeedback.task.task_id)}`}
                        className="rounded-md border border-emerald-300 bg-white px-2 py-1 font-medium text-emerald-800 hover:border-emerald-500"
                      >
                        {t("tasks.open_run")}
                      </Link>
                    ) : null}
                    <Link
                      data-testid="task-create-audit-link"
                      href={`/tasks/${encodeURIComponent(createFeedback.task.task_id)}`}
                      className="rounded-md border border-emerald-300 bg-white px-2 py-1 font-medium text-emerald-800 hover:border-emerald-500"
                    >
                      {t("tasks.open_execution_audit")}
                    </Link>
                  </div>
                </div>
              ) : (
                <div data-testid="task-create-error">{createFeedback.message}</div>
              )}
            </div>
          ) : null}
        </div>

        <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden">
          <div className="border-b border-zinc-200 px-4 py-3">
            <div className="text-sm font-semibold">{t("tasks.persisted_list")}</div>
            <div className="text-xs text-zinc-500">
              {totalTasks && totalTasks > tasks.length
                ? `${tasks.length} / ${totalTasks}`
                : tasks.length}{" "}
              / {agents.length} agents
            </div>
          </div>
          <table data-testid="tasks-table" className="w-full text-sm">
            <thead className="bg-zinc-50 text-zinc-600">
              <tr>
                <th className="px-4 py-3 text-left font-medium">{t("tasks.table.task")}</th>
                <th className="px-4 py-3 text-left font-medium">{t("tasks.table.status")}</th>
                <th className="px-4 py-3 text-left font-medium">{t("tasks.table.assigned")}</th>
                <th className="px-4 py-3 text-left font-medium">{t("tasks.table.updated")}</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => {
                const taskHref = `/tasks/${encodeURIComponent(task.task_id)}`;
                const linkLabel = `Open task ${task.title}`;
                return (
                  <tr
                    key={task.task_id}
                    data-testid={`task-row-${task.task_id}`}
                    className="cursor-pointer border-t border-zinc-200 hover:bg-zinc-50"
                  >
                    <td className="relative align-top">
                      <Link
                        data-testid={`task-link-${task.task_id}`}
                        href={taskHref}
                        aria-label={linkLabel}
                        className="absolute inset-0 focus:outline-none focus-visible:bg-zinc-50"
                      />
                      <div className="pointer-events-none px-4 py-3">
                        <div className="font-medium hover:underline">{task.title}</div>
                        <div className="mt-1 text-xs text-zinc-500">
                          <span className="font-mono">{task.task_id}</span> / {task.execution_mode} / priority=
                          {task.queue_priority}
                        </div>
                        {task.last_error ? (
                          <div className="mt-2 rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-xs text-rose-700">
                            {task.last_error}
                          </div>
                        ) : null}
                      </div>
                    </td>
                    <td className="relative align-top">
                      <Link
                        href={taskHref}
                        aria-label={linkLabel}
                        className="absolute inset-0 focus:outline-none focus-visible:bg-zinc-50"
                      />
                      <div className="pointer-events-none px-4 py-3">
                        <span className="rounded-full border border-zinc-200 px-2 py-1 text-xs">
                          {task.status}
                        </span>
                        <div className="mt-2 text-xs text-zinc-500">
                          {t("tasks.retries")}: {task.retry_count}
                        </div>
                        <div className="mt-1 text-xs text-zinc-500">priority: {task.queue_priority}</div>
                      </div>
                    </td>
                    <td className="relative align-top text-zinc-700">
                      <Link
                        href={taskHref}
                        aria-label={linkLabel}
                        className="absolute inset-0 focus:outline-none focus-visible:bg-zinc-50"
                      />
                      <div className="pointer-events-none px-4 py-3">
                        {task.assigned_agent_id ?? t("tasks.unassigned")}
                      </div>
                    </td>
                    <td className="relative align-top text-zinc-700">
                      <Link
                        href={taskHref}
                        aria-label={linkLabel}
                        className="absolute inset-0 focus:outline-none focus-visible:bg-zinc-50"
                      />
                      <div className="pointer-events-none px-4 py-3">
                        {task.updated_at ?? task.created_at}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
