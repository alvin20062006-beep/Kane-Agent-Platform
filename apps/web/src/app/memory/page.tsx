"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { apiGet, apiPost } from "@/lib/api";
import { useT } from "@/lib/i18n/LocaleProvider";
import type { ListResponse, MemoryItem } from "@/lib/octopus-types";

type Tab = "approved" | "candidate" | "external";

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

const STATUS_COLOR: Record<string, string> = {
  approved: "bg-green-50 border-green-200 text-green-700",
  candidate: "bg-amber-50 border-amber-200 text-amber-700",
  rejected: "bg-zinc-50 border-zinc-200 text-zinc-500",
};

function MemoryCard({
  item,
  onApprove,
  onReject,
  onDelete,
}: {
  item: MemoryItem;
  onApprove?: () => void;
  onReject?: () => void;
  onDelete?: () => void;
}) {
  const t = useT();
  const [busy, setBusy] = useState(false);

  const STATUS_LABEL: Record<string, string> = {
    approved: t("memory.state.approved"),
    candidate: t("memory.state.candidate"),
    rejected: t("memory.state.rejected"),
  };

  const handle = async (action: () => Promise<void>) => {
    setBusy(true);
    try {
      await action();
    } finally {
      setBusy(false);
    }
  };

  const src = item as MemoryItem & {
    source_agent_id?: string;
    task_id?: string;
    conversation_id?: string;
    created_at?: string;
  };

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold truncate">{item.title}</div>
          <div className="mt-0.5 text-xs text-zinc-400 font-mono">{item.memory_id}</div>
        </div>
        <span
          className={cx(
            "shrink-0 rounded-full border px-2 py-0.5 text-xs",
            STATUS_COLOR[item.status]
          )}
        >
          {STATUS_LABEL[item.status] ?? item.status}
        </span>
      </div>

      <div className="text-xs text-zinc-600 whitespace-pre-wrap line-clamp-3">
        {item.content}
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-zinc-400">
        {src.source_agent_id && (
          <div>
            {t("memory.field.source_agent")}:{" "}
            <span className="text-zinc-600 font-mono">{src.source_agent_id}</span>
          </div>
        )}
        {src.task_id && (
          <div>
            {t("memory.field.task")}:{" "}
            <span className="text-zinc-600 font-mono">{src.task_id}</span>
          </div>
        )}
        {src.conversation_id && (
          <div>
            {t("memory.field.conversation")}:{" "}
            <span className="text-zinc-600 font-mono">{src.conversation_id}</span>
          </div>
        )}
        {src.created_at && (
          <div>
            {t("memory.field.time")}: {src.created_at.slice(0, 16)}
          </div>
        )}
        <div>
          {t("memory.field.type")}: {item.memory_type} · {t("memory.field.scope")}:{" "}
          {item.scope_type ?? "—"}
        </div>
        <div>
          {t("memory.field.confidence")}: {item.confidence}
        </div>
      </div>

      {item.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {item.tags.map((tag) => (
            <span
              key={tag}
              className="rounded-full border border-zinc-200 px-2 py-0.5 text-xs text-zinc-500"
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      <div className="flex flex-wrap gap-2 pt-1">
        {onApprove && (
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              handle(async () => {
                await apiPost(`/memory/candidates/${item.memory_id}/approve`, {});
                onApprove();
              })
            }
            className="rounded-md bg-green-600 px-3 py-1 text-xs text-white disabled:opacity-50 hover:bg-green-700"
          >
            {t("memory.action.approve")}
          </button>
        )}
        {onReject && (
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              handle(async () => {
                await apiPost(`/memory/candidates/${item.memory_id}/reject`, {});
                onReject();
              })
            }
            className="rounded-md border border-zinc-300 px-3 py-1 text-xs text-zinc-600 disabled:opacity-50 hover:bg-zinc-50"
          >
            {t("memory.action.reject")}
          </button>
        )}
        {onDelete && (
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              if (!confirm(t("memory.confirm.delete"))) return;
              handle(async () => {
                await fetch(
                  `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/memory/${item.memory_id}`,
                  { method: "DELETE" }
                );
                onDelete();
              });
            }}
            className="ml-auto rounded-md border border-red-200 px-3 py-1 text-xs text-red-600 disabled:opacity-50 hover:bg-red-50"
          >
            {t("memory.action.delete")}
          </button>
        )}
      </div>
    </div>
  );
}

function MemoryPageInner() {
  const t = useT();
  const searchParams = useSearchParams();
  const initialTab = (() => {
    const v = searchParams.get("tab");
    return v === "candidate" || v === "external" || v === "approved" ? (v as Tab) : "approved";
  })();

  const [all, setAll] = useState<MemoryItem[]>([]);
  const [activeTab, setActiveTab] = useState<Tab>(initialTab);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiGet<ListResponse<MemoryItem>>("/memory");
      setAll(data.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const approved = all.filter((m) => m.status === "approved");
  const candidates = all.filter((m) => m.status === "candidate");
  const external = all.filter((m) => {
    const s = m as MemoryItem & { source_agent_id?: string };
    return s.source_agent_id && s.source_agent_id !== "octopus_builtin";
  });

  const tabs: { id: Tab; label: string; count: number }[] = [
    { id: "approved", label: t("memory.tab.approved"), count: approved.length },
    { id: "candidate", label: t("memory.tab.candidate"), count: candidates.length },
    { id: "external", label: t("memory.tab.external"), count: external.length },
  ];

  const displayItems =
    activeTab === "approved" ? approved : activeTab === "candidate" ? candidates : external;

  const handleExport = async () => {
    try {
      const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
      const res = await fetch(
        `${base}/memory/export?status=${activeTab === "candidate" ? "candidate" : "approved"}`
      );
      const data = await res.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `memory-export-${activeTab}-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(t("memory.export_failed").replace("{err}", String(e)));
    }
  };

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-zinc-900">
            {t("memory.title")}
          </h1>
          <p className="mt-1 text-sm text-zinc-600">{t("memory.subtitle")}</p>
        </div>
        <button
          type="button"
          onClick={handleExport}
          className="shrink-0 rounded-md border border-zinc-300 px-3 py-1.5 text-xs text-zinc-600 hover:bg-zinc-50"
        >
          {t("memory.action.export_tab")}
        </button>
      </div>

      <div className="flex gap-1 border-b border-zinc-200">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ${
              activeTab === tab.id
                ? "border-zinc-900 text-zinc-900"
                : "border-transparent text-zinc-500 hover:text-zinc-700"
            }`}
          >
            {tab.label}
            {tab.count > 0 && (
              <span className="ml-1.5 rounded-full bg-zinc-200 px-1.5 py-0.5 text-xs text-zinc-600">
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {loading && (
        <div className="py-8 text-center text-sm text-zinc-400">
          {t("common.loading")}
        </div>
      )}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {t("memory.load_failed").replace("{err}", error)}
        </div>
      )}
      {!loading && !error && displayItems.length === 0 && (
        <div className="py-8 text-center text-sm text-zinc-400">{t("common.empty")}</div>
      )}
      {!loading && !error && displayItems.length > 0 && (
        <div className="space-y-3">
          {displayItems.map((item) => (
            <MemoryCard
              key={item.memory_id}
              item={item}
              onApprove={activeTab === "candidate" ? load : undefined}
              onReject={activeTab === "candidate" ? load : undefined}
              onDelete={load}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function MemoryPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-zinc-400">Loading…</div>}>
      <MemoryPageInner />
    </Suspense>
  );
}
