"use client";

import { useEffect, useState } from "react";

import { apiGet } from "@/lib/api";
import type { Task } from "@/lib/octopus-types";

type Props = {
  taskId: string;
  initialTask: Task;
};

export function TaskStatusLive({ taskId, initialTask }: Props) {
  const [task, setTask] = useState<Task>(initialTask);

  useEffect(() => {
    let cancelled = false;
    const interval = setInterval(() => {
      apiGet<{ data: Task }>(`/tasks/${encodeURIComponent(taskId)}`)
        .then((res) => {
          if (cancelled) return;
          setTask(res.data);
        })
        .catch(() => undefined);
    }, 1200);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [taskId]);

  return (
    <>
      <div>
        <div className="text-xs text-zinc-500">Status</div>
        <div data-testid="task-status-value" className="mt-1">
          {task.status}
        </div>
      </div>
      <div>
        <div className="text-xs text-zinc-500">Last run</div>
        <div data-testid="task-last-run-value" className="mt-1">
          {task.last_run_id ?? "None yet"}
        </div>
      </div>
      {task.last_error ? (
        <div className="md:col-span-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          <div className="font-medium">Last error</div>
          <div className="mt-1">{task.last_error}</div>
        </div>
      ) : null}
      <div className="md:col-span-2">
        <div className="text-xs text-zinc-500">Result</div>
        <div data-testid="task-result-summary" className="mt-2 text-sm text-zinc-700 whitespace-pre-wrap">
          {task.result_summary || "No result summary yet."}
        </div>
      </div>
    </>
  );
}

