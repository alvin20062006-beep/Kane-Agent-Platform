"use client";

import { useEffect, useState } from "react";

import { JsonCard } from "@/components/json-card";
import { apiGet, apiPost } from "@/lib/api";
import type {
  ActiveMemorySnapshot,
  ListResponse,
  MemoryEvent,
  MemoryIndexEntry,
  RetrievalResult,
} from "@/lib/octopus-types";

const EXACT_KEYS = [
  "subject_key",
  "task_id",
  "run_id",
  "event_id",
  "memory_id",
  "skill_id",
  "decision_id",
  "failure_id",
  "conversation_id",
] as const;

type ExactKey = (typeof EXACT_KEYS)[number];

function Badge({ value }: { value: string | number | boolean | null | undefined }) {
  return (
    <span className="inline-flex rounded-full border border-zinc-200 bg-zinc-50 px-2 py-0.5 text-[11px] font-medium text-zinc-600">
      {String(value ?? "none")}
    </span>
  );
}

function Empty({ label }: { label: string }) {
  return <div className="rounded-md border border-dashed border-zinc-200 p-3 text-sm text-zinc-500">{label}</div>;
}

export function MemoryLedgerAuditPanel() {
  const [events, setEvents] = useState<MemoryEvent[]>([]);
  const [index, setIndex] = useState<MemoryIndexEntry[]>([]);
  const [snapshot, setSnapshot] = useState<ActiveMemorySnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [eventsResp, indexResp, snapshotResp] = await Promise.all([
        apiGet<ListResponse<MemoryEvent>>("/memory/events?limit=50"),
        apiGet<ListResponse<MemoryIndexEntry>>("/memory/index"),
        apiGet<{ data: ActiveMemorySnapshot }>("/memory/snapshot"),
      ]);
      setEvents(eventsResp.items);
      setIndex(indexResp.items);
      setSnapshot(snapshotResp.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-zinc-900">Memory Ledger / Snapshot Audit</h2>
          <p className="mt-1 text-xs text-zinc-500">
            UI audit view only. The ledger is historical evidence and is not injected into prompts.
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
        >
          {loading ? "Refreshing" : "Refresh"}
        </button>
      </div>
      {error ? <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div> : null}

      <section className="rounded-lg border border-zinc-200 bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm font-semibold">Active Snapshot</div>
          <Badge value={snapshot ? `${snapshot.memory_ids.length} memories` : "not_loaded"} />
        </div>
        <p className="mt-1 text-xs text-zinc-500">
          Prompt-eligible projection: active snapshot plus relevant evidence, not the full append-only ledger.
        </p>
        <div className="mt-3">
          {snapshot ? <JsonCard data={snapshot} /> : <Empty label="No active snapshot loaded." />}
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-sm font-semibold">Memory Index</div>
          <div className="mt-3 space-y-2">
            {index.length ? (
              index.slice(0, 30).map((entry) => (
                <div key={entry.index_id} className="rounded-md border border-zinc-200 p-3 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="break-all font-mono text-xs">{entry.memory_id}</span>
                    <Badge value={entry.status} />
                  </div>
                  <div className="mt-2 text-xs text-zinc-600">{entry.title ?? entry.memory_type ?? "untitled"}</div>
                  <div className="mt-1 break-all text-xs text-zinc-500">{entry.subject_key ?? "no subject_key"}</div>
                </div>
              ))
            ) : (
              <Empty label="No index entries." />
            )}
          </div>
        </div>

        <div className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-sm font-semibold">Memory Events</div>
          <div className="mt-3 space-y-2">
            {events.length ? (
              events.map((event) => (
                <div key={event.event_id} className="rounded-md border border-zinc-200 p-3 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="break-all font-mono text-xs">{event.event_id}</span>
                    <Badge value={event.event_type} />
                  </div>
                  <div className="mt-2 grid gap-1 text-xs text-zinc-600 md:grid-cols-2">
                    <div>created_by: {event.created_by}</div>
                    <div>memory_id: {event.memory_id ?? "none"}</div>
                    <div>run_id: {event.run_id ?? "none"}</div>
                    <div>run_step_id: {event.run_step_id ?? "none"}</div>
                  </div>
                </div>
              ))
            ) : (
              <Empty label="No memory events." />
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

export function RetrievalDebugPanel() {
  const [exactKeyType, setExactKeyType] = useState<ExactKey>("subject_key");
  const [exactKey, setExactKey] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [runtimeQuery, setRuntimeQuery] = useState("");
  const [runtimeTaskId, setRuntimeTaskId] = useState("");
  const [runtimeRunId, setRuntimeRunId] = useState("");
  const [result, setResult] = useState<RetrievalResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = async (mode: "exact" | "search" | "runtime") => {
    setBusy(mode);
    setError(null);
    try {
      if (mode === "exact") {
        const response = await apiPost<{ data: RetrievalResult }>("/memory/retrieve/exact", {
          key_type: exactKeyType,
          key: exactKey,
          limit: 10,
          max_chars: 12000,
        });
        setResult(response.data);
      } else if (mode === "search") {
        const response = await apiPost<{ data: RetrievalResult }>("/memory/retrieve/search", {
          query: searchQuery,
          limit: 10,
          max_chars: 12000,
        });
        setResult(response.data);
      } else {
        const response = await apiPost<{ data: RetrievalResult }>("/memory/retrieve/runtime-context", {
          query: runtimeQuery || null,
          task_id: runtimeTaskId || null,
          run_id: runtimeRunId || null,
          evidence_limit: 8,
          max_chars: 12000,
        });
        setResult(response.data);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold text-zinc-900">Retrieval Debug</h2>
        <p className="mt-1 text-xs text-zinc-500">
          Inspect Exact Retrieval, Native Evidence Search, and Runtime Context outputs without changing retrieval behavior.
        </p>
      </div>

      <section className="grid gap-4 xl:grid-cols-3">
        <div className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-sm font-semibold">Exact Retrieval</div>
          <div className="mt-3 space-y-3">
            <select
              value={exactKeyType}
              onChange={(event) => setExactKeyType(event.target.value as ExactKey)}
              className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm"
              aria-label="Exact retrieval key type"
            >
              {EXACT_KEYS.map((key) => (
                <option key={key} value={key}>
                  {key}
                </option>
              ))}
            </select>
            <input
              value={exactKey}
              onChange={(event) => setExactKey(event.target.value)}
              className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm"
              placeholder="key"
            />
            <button
              type="button"
              onClick={() => submit("exact")}
              disabled={!exactKey.trim() || busy === "exact"}
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
            >
              Run exact
            </button>
          </div>
        </div>

        <div className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-sm font-semibold">Native Evidence Search</div>
          <div className="mt-3 space-y-3">
            <textarea
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              className="min-h-24 w-full rounded-md border border-zinc-300 px-3 py-2 text-sm"
              placeholder="query"
            />
            <button
              type="button"
              onClick={() => submit("search")}
              disabled={!searchQuery.trim() || busy === "search"}
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
            >
              Run search
            </button>
          </div>
        </div>

        <div className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-sm font-semibold">Runtime Context</div>
          <div className="mt-3 space-y-3">
            <input
              value={runtimeQuery}
              onChange={(event) => setRuntimeQuery(event.target.value)}
              className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm"
              placeholder="query optional"
            />
            <input
              value={runtimeTaskId}
              onChange={(event) => setRuntimeTaskId(event.target.value)}
              className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm"
              placeholder="task_id optional"
            />
            <input
              value={runtimeRunId}
              onChange={(event) => setRuntimeRunId(event.target.value)}
              className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm"
              placeholder="run_id optional"
            />
            <button
              type="button"
              onClick={() => submit("runtime")}
              disabled={busy === "runtime"}
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
            >
              Build context
            </button>
          </div>
        </div>
      </section>

      {error ? <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div> : null}
      <section className="rounded-lg border border-zinc-200 bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm font-semibold">Result</div>
          {result ? (
            <div className="flex gap-2">
              <Badge value={`used ${result.used_chars ?? "unknown"}`} />
              <Badge value={result.truncated ? "truncated" : "not_truncated"} />
            </div>
          ) : null}
        </div>
        <div className="mt-3">
          {result ? <JsonCard data={result} /> : <Empty label="Run a retrieval debug query to inspect results." />}
        </div>
      </section>
    </div>
  );
}
