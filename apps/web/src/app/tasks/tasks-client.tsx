"use client";

import Link from "next/link";
import { useState } from "react";

import { useT } from "@/lib/i18n/LocaleProvider";
import { listModesFor, type ExecutionMode } from "@/lib/modes";
import { apiPost } from "@/lib/api";
import type { Agent, Task } from "@/lib/octopus-types";

type Props = {
  initialTasks: Task[];
  agents: Agent[];
};

export function TasksClient({ initialTasks, agents }: Props) {
  const t = useT();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  // Tasks 页面默认假设操作者是 Kanaloa（内置），否则 direct_agent
  // 用户真正想用外部 Agent 会在对话里 ⋯ 菜单切换 + 升级为任务
  const [executionMode, setExecutionMode] = useState<ExecutionMode>("commander");
  const [busy, setBusy] = useState(false);
  const [responseText, setResponseText] = useState("");
  const [tasks, setTasks] = useState(initialTasks);

  const createTask = async () => {
    setBusy(true);
    setResponseText("");
    try {
      const response = await apiPost<{ data: Task }>("/tasks", {
        title: title.trim() || "Untitled beta task",
        description: description.trim() || null,
        execution_mode: executionMode,
      });
      setTasks([response.data, ...tasks]);
      setResponseText(JSON.stringify(response, null, 2));
      setTitle("");
      setDescription("");
    } catch (error) {
      setResponseText(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  // 默认任务创建场景假定 Kanaloa 可承接所有模式
  const modes = listModesFor(true);

  return (
    <div className="space-y-6">
      <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-900">
        <span className="font-semibold">{t("common.beta")}</span>
        <span className="mx-2">·</span>
        <span>{t("tasks.beta_notice")}</span>
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
            <div className="mb-1 text-xs text-zinc-600">
              {t("tasks.description_label")}
            </div>
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
          <button
            data-testid="create-task-button"
            type="button"
            disabled={busy}
            onClick={createTask}
            className="rounded-md bg-zinc-900 px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            {busy ? t("tasks.creating") : t("tasks.create")}
          </button>
          {responseText ? (
            <pre
              data-testid="task-create-response"
              className="max-h-[220px] overflow-auto whitespace-pre-wrap rounded-md bg-zinc-950 p-3 text-xs text-zinc-100"
            >
              {responseText}
            </pre>
          ) : null}
        </div>

        <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden">
          <div className="border-b border-zinc-200 px-4 py-3">
            <div className="text-sm font-semibold">{t("tasks.persisted_list")}</div>
            <div className="text-xs text-zinc-500">
              {tasks.length} · {agents.length} agents
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
              {tasks.map((task) => (
                <tr key={task.task_id} className="border-t border-zinc-200">
                  <td className="px-4 py-3 align-top">
                    <div className="font-medium">
                      <Link
                        data-testid={`task-link-${task.task_id}`}
                        href={`/tasks/${encodeURIComponent(task.task_id)}`}
                        className="hover:underline"
                      >
                        {task.title}
                      </Link>
                    </div>
                    <div className="mt-1 text-xs text-zinc-500">
                      <span className="font-mono">{task.task_id}</span> · {task.execution_mode}
                    </div>
                    {task.last_error ? (
                      <div className="mt-2 rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-xs text-rose-700">
                        {task.last_error}
                      </div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 align-top">
                    <span className="rounded-full border border-zinc-200 px-2 py-1 text-xs">
                      {task.status}
                    </span>
                    <div className="mt-2 text-xs text-zinc-500">
                      {t("tasks.retries")}: {task.retry_count}
                    </div>
                  </td>
                  <td className="px-4 py-3 align-top text-zinc-700">
                    {task.assigned_agent_id ?? t("tasks.unassigned")}
                  </td>
                  <td className="px-4 py-3 align-top text-zinc-700">
                    {task.updated_at ?? task.created_at}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
