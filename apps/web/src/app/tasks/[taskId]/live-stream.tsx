"use client";

import { useEffect, useMemo, useState } from "react";

import { getApiBaseUrl } from "@/lib/api";
import type { RunLogLine, TaskEvent } from "@/lib/octopus-types";

type Props = {
  taskId: string;
  lastRunId?: string | null;
};

export function LiveStream({ taskId, lastRunId }: Props) {
  const [liveEvents, setLiveEvents] = useState<TaskEvent[]>([]);
  const [liveLogs, setLiveLogs] = useState<RunLogLine[]>([]);

  const eventsUrl = useMemo(
    () => `${getApiBaseUrl()}/tasks/${encodeURIComponent(taskId)}/events/stream`,
    [taskId]
  );
  const logsUrl = useMemo(() => {
    if (!lastRunId) return null;
    return `${getApiBaseUrl()}/runs/${encodeURIComponent(lastRunId)}/logs/stream`;
  }, [lastRunId]);

  useEffect(() => {
    const es = new EventSource(eventsUrl);
    es.addEventListener("task_event", (evt) => {
      try {
        const data = JSON.parse((evt as MessageEvent).data);
        setLiveEvents((prev) => {
          if (prev.some((e) => e.event_id === data.event_id)) return prev;
          return [...prev, data].slice(-100);
        });
      } catch {
        // ignore
      }
    });
    return () => es.close();
  }, [eventsUrl]);

  useEffect(() => {
    if (!logsUrl) return;
    const es = new EventSource(logsUrl);
    es.addEventListener("run_log", (evt) => {
      try {
        const data = JSON.parse((evt as MessageEvent).data);
        setLiveLogs((prev) => {
          if (prev.some((l) => l.log_id === data.log_id)) return prev;
          return [...prev, data].slice(-200);
        });
      } catch {
        // ignore
      }
    });
    return () => es.close();
  }, [logsUrl]);

  return (
    <section className="grid gap-4 xl:grid-cols-2">
      <div data-testid="task-live-events" className="rounded-lg border border-zinc-200 bg-white p-4">
        <div className="text-sm font-semibold">Live events (SSE)</div>
        <div className="mt-3 space-y-2 max-h-[280px] overflow-auto">
          {liveEvents.length ? (
            liveEvents.map((e) => (
              <div key={e.event_id} className="rounded-md border border-zinc-200 p-3 text-sm">
                <div className="font-medium">{e.type}</div>
                <div className="mt-1 text-xs text-zinc-500">{e.created_at}</div>
                {e.message ? <div className="mt-2 text-zinc-700">{e.message}</div> : null}
              </div>
            ))
          ) : (
            <div className="text-sm text-zinc-500">Waiting for events…</div>
          )}
        </div>
      </div>

      <div className="rounded-lg border border-zinc-200 bg-white p-4">
        <div className="text-sm font-semibold">Live run logs (SSE)</div>
        <div className="mt-3 space-y-2 max-h-[280px] overflow-auto">
          {lastRunId ? null : (
            <div className="text-sm text-zinc-500">No run yet.</div>
          )}
          {liveLogs.map((l) => (
            <div key={l.log_id} className="rounded-md border border-zinc-200 p-3 text-sm">
              <div className="flex items-center justify-between gap-3">
                <div className="font-medium">
                  #{l.seq} {l.level}
                </div>
                <div className="text-xs text-zinc-500">{l.created_at}</div>
              </div>
              <div className="mt-2 text-zinc-700 whitespace-pre-wrap">{l.message}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

