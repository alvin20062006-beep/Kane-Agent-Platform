"use client";

import { useState } from "react";

import { apiGet, apiPost, getApiBaseUrl } from "@/lib/api";
import { useT } from "@/lib/i18n/LocaleProvider";
import type { Agent, Task } from "@/lib/octopus-types";

type Props = {
  taskId: string;
  agents: Agent[];
  currentAgentId?: string | null;
  taskStatus: string;
  executionMode: "commander" | "pilot" | "direct_agent";
  pendingApprovalId?: string | null;
};

export function TaskActions({
  taskId,
  agents,
  currentAgentId,
  taskStatus,
  executionMode,
  pendingApprovalId,
}: Props) {
  const t = useT();
  const [selectedAgentId, setSelectedAgentId] = useState(
    currentAgentId ?? agents[0]?.agent_id ?? "octopus_builtin"
  );
  const [log, setLog] = useState("");
  const [busy, setBusy] = useState(false);
  const [approvalNote, setApprovalNote] = useState("");

  const waitForTaskStatus = async (predicate: (t: Task) => boolean) => {
    const startedAt = Date.now();
    const timeoutMs = 30_000;
    while (Date.now() - startedAt < timeoutMs) {
      try {
        const detail = await apiGet<{ data: Task }>(
          `/tasks/${encodeURIComponent(taskId)}`
        );
        if (predicate(detail.data)) {
          return;
        }
      } catch {
        // ignore transient errors during reload window
      }
      await new Promise((r) => setTimeout(r, 800));
    }
  };

  const runRequest = async (path: string, body?: unknown, reload = true) => {
    setBusy(true);
    setLog("");
    try {
      const response = await apiPost<unknown>(
        `/tasks/${encodeURIComponent(taskId)}${path}`,
        body
      );
      setLog(JSON.stringify(response, null, 2));
      if (reload) {
        // The API run/worker is async; waiting briefly prevents UI from "sticking" on queued/running.
        if (path === "/assign") {
          await waitForTaskStatus((t) => t.status === "assigned");
        } else if (path === "/run") {
          await waitForTaskStatus(
            (t) =>
              t.status === "succeeded" ||
              t.status === "failed" ||
              t.status === "waiting_approval"
          );
        } else if (path === "/retry") {
          await waitForTaskStatus((t) => t.status === "assigned" || t.status === "created");
        } else {
          await waitForTaskStatus(() => true);
        }
        window.location.reload();
      }
    } catch (error) {
      setLog(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold">{t("task_detail.actions")}</div>
          <div className="text-xs text-zinc-500">
            {t("task_detail.api_base")}: <span className="font-mono">{getApiBaseUrl()}</span>
          </div>
          <div className="mt-1 text-xs text-zinc-500">
            {t("task_detail.mode")}: <span className="font-mono">{executionMode}</span> •{" "}
            {t("task_detail.status")}: <span className="font-mono">{taskStatus}</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            data-testid="assign-agent-select"
            className="rounded-md border border-zinc-200 px-3 py-2 text-sm"
            value={selectedAgentId}
            onChange={(event) => setSelectedAgentId(event.target.value)}
          >
            {agents.map((agent) => (
              <option key={agent.agent_id} value={agent.agent_id}>
                {agent.display_name} ({agent.adapter_id ?? agent.type})
              </option>
            ))}
          </select>
          <button
            data-testid="assign-task-button"
            type="button"
            disabled={busy}
            onClick={() =>
              runRequest("/assign", {
                agent_id: selectedAgentId,
              })
            }
            className="rounded-md border border-zinc-200 px-3 py-2 text-sm disabled:opacity-50"
          >
            {t("task_detail.assign")}
          </button>
          <button
            data-testid="run-task-button"
            type="button"
            disabled={busy}
            onClick={() => runRequest("/run")}
            className="rounded-md bg-[var(--octo-royal-blue)] px-3 py-2 text-sm text-white disabled:opacity-50"
          >
            {t("task_detail.run")}
          </button>
          {pendingApprovalId ? (
            <button
              data-testid="approve-task-button"
              type="button"
              disabled={busy}
              onClick={() => runRequest("/approve", { note: approvalNote })}
              className="rounded-md border border-emerald-200 px-3 py-2 text-sm text-emerald-800 disabled:opacity-50"
            >
              {t("task_detail.approve")}
            </button>
          ) : null}
          {pendingApprovalId ? (
            <button
              data-testid="reject-task-button"
              type="button"
              disabled={busy}
              onClick={() => runRequest("/reject", { reason: approvalNote })}
              className="rounded-md border border-rose-200 px-3 py-2 text-sm text-rose-800 disabled:opacity-50"
            >
              {t("task_detail.reject")}
            </button>
          ) : null}
          <button
            data-testid="retry-only-button"
            type="button"
            disabled={busy}
            onClick={() => runRequest("/retry")}
            className="rounded-md border border-emerald-200 px-3 py-2 text-sm text-emerald-800 disabled:opacity-50"
          >
            {t("task_detail.retry_only")}
          </button>
          <button
            data-testid="retry-task-button"
            type="button"
            disabled={busy}
            onClick={async () => {
              await runRequest("/retry", undefined, false);
              await runRequest("/run");
            }}
            className="rounded-md border border-emerald-200 px-3 py-2 text-sm text-emerald-800 disabled:opacity-50"
          >
            {t("task_detail.retry_run")}
          </button>
          <button
            data-testid="mark-failed-button"
            type="button"
            disabled={busy}
            onClick={() =>
              runRequest("/fail", { reason: "operator_mark_failed_from_ui" })
            }
            className="rounded-md border border-rose-200 px-3 py-2 text-sm text-rose-800 disabled:opacity-50"
          >
            {t("task_detail.mark_failed")}
          </button>
        </div>
      </div>
      {pendingApprovalId ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm">
          <div className="font-medium text-amber-900">{t("task_detail.pending_approval")}</div>
          <div className="mt-1 text-xs text-amber-900/80 font-mono">
            {pendingApprovalId}
          </div>
          <div className="mt-2">
            <div className="mb-1 text-xs text-amber-900/70">{t("task_detail.approval_note")}</div>
            <input
              value={approvalNote}
              onChange={(e) => setApprovalNote(e.target.value)}
              className="w-full rounded-md border border-amber-200 bg-white px-3 py-2 text-sm"
              placeholder={t("task_detail.approval_note_placeholder")}
            />
          </div>
        </div>
      ) : null}
      {log ? (
        <pre
          data-testid="task-actions-log"
          className="max-h-[220px] overflow-auto whitespace-pre-wrap rounded-md bg-zinc-950 p-3 text-xs text-zinc-100"
        >
          {log}
        </pre>
      ) : null}
    </div>
  );
}
