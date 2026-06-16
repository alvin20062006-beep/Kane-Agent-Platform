"use client";

import { useState } from "react";

import { ProductNotice } from "@/components/product-notice";
import { PageTitle } from "@/components/page-title";
import { apiPost } from "@/lib/api";
import type { ExecutionReceipt, GovernorDecision, GovernorSummary } from "@/lib/octopus-types";

const RISK_COLORS: Record<string, string> = {
  low: "text-green-700 bg-green-50 border-green-200",
  medium: "text-yellow-700 bg-yellow-50 border-yellow-200",
  high: "text-red-700 bg-red-50 border-red-200",
};

const DECISION_COLORS: Record<string, string> = {
  auto_execute: "text-blue-700 bg-blue-50 border-blue-200",
  require_confirmation: "text-yellow-700 bg-yellow-50 border-yellow-200",
  deny: "text-red-700 bg-red-50 border-red-200",
};

const STATUS_COLORS: Record<string, string> = {
  pending: "text-yellow-700 bg-yellow-50 border-yellow-200",
  confirmed: "text-blue-700 bg-blue-50 border-blue-200",
  executed: "text-green-700 bg-green-50 border-green-200",
  denied: "text-red-700 bg-red-50 border-red-200",
  failed: "text-red-700 bg-red-50 border-red-200",
};

function Badge({ label, colorClass }: { label: string; colorClass: string }) {
  return (
    <span className={`inline-block rounded-full border px-2 py-0.5 text-xs font-medium ${colorClass}`}>
      {label}
    </span>
  );
}

function DecisionCard({
  decision,
  onConfirmed,
}: {
  decision: GovernorDecision;
  onConfirmed: (receipt: ExecutionReceipt) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canConfirm =
    decision.status === "pending" && decision.decision === "require_confirmation";

  const handleConfirm = async () => {
    setBusy(true);
    setError(null);
    try {
      const resp = await apiPost<{ receipt: ExecutionReceipt }>(
        `/governor/decisions/${decision.decision_id}/confirm`,
        {}
      );
      onConfirmed(resp.receipt);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      data-testid="governor-decision-card"
      className="rounded-lg border border-zinc-200 bg-white p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-sm">{decision.action_id}</span>
            <Badge
              label={decision.decision}
              colorClass={DECISION_COLORS[decision.decision] ?? ""}
            />
            <Badge
              label={`risk=${decision.risk_level}`}
              colorClass={RISK_COLORS[decision.risk_level] ?? ""}
            />
            <Badge
              label={decision.status}
              colorClass={STATUS_COLORS[decision.status] ?? ""}
            />
          </div>
          <div className="mt-1 text-xs text-zinc-500">{decision.reason}</div>
        </div>
        <div className="text-xs text-zinc-400">{decision.created_at}</div>
      </div>

      <div className="mt-2 flex flex-wrap gap-2 text-xs text-zinc-500">
        <span className="rounded border border-zinc-200 px-2 py-0.5">
          gates_passed={decision.gates_passed.join(", ") || "none"}
        </span>
        {decision.gates_failed.length > 0 ? (
          <span className="rounded border border-red-200 bg-red-50 px-2 py-0.5 text-red-700">
            gates_failed={decision.gates_failed.join(", ")}
          </span>
        ) : null}
      </div>

      {decision.source_task_id ? (
        <div className="mt-1 text-xs text-zinc-400">task: {decision.source_task_id}</div>
      ) : null}

      {canConfirm ? (
        <div className="mt-3">
          <button
            data-testid="governor-confirm-button"
            onClick={handleConfirm}
            disabled={busy}
            className="rounded-md border border-blue-300 bg-blue-50 px-4 py-2 text-sm font-medium text-blue-700 hover:bg-blue-100 disabled:opacity-50"
          >
            {busy ? "Confirming…" : "Confirm & Execute"}
          </button>
          {error ? (
            <div className="mt-2 text-xs text-red-700">{error}</div>
          ) : null}
        </div>
      ) : null}

      {decision.executed_at ? (
        <div className="mt-2 text-xs text-zinc-400">executed: {decision.executed_at}</div>
      ) : null}
    </div>
  );
}

export function GovernorClient({ summary }: { summary: GovernorSummary }) {
  const [pendingDecisions, setPendingDecisions] = useState<GovernorDecision[]>(
    summary.pending_decisions
  );

  const handleConfirmed = (receipt: ExecutionReceipt) => {
    setPendingDecisions((prev) =>
      prev.filter((d) => d.decision_id !== receipt.decision_id)
    );
  };

  const metricCards: Array<[string, string, string | number]> = [
    ["total", "Total decisions", summary.totals.total],
    ["pending", "Pending confirm", summary.totals.pending],
    ["executed", "Executed", summary.totals.executed],
    ["denied", "Denied", summary.totals.denied],
    ["failed", "Failed", summary.totals.failed],
    ["auto_executed", "Auto-executed", summary.totals.auto_executed],
  ];

  return (
    <div className="space-y-6 p-6">
      <PageTitle
        title="Governor"
        subtitle="P3 controlled execution layer. Evaluates advisor suggestions through safety gates before acting."
      />
      <ProductNotice note="Governor is read-auditable. Actions execute only within the allowlist (retry_run, acknowledge_escalation, resolve_escalation, adjust_queue_priority). High-risk decisions are always denied." />

      <div className="flex flex-wrap gap-3">
        <span
          className={`rounded-full border px-3 py-1 text-xs font-medium ${
            summary.governor_enabled
              ? "border-green-200 bg-green-50 text-green-700"
              : "border-red-200 bg-red-50 text-red-700"
          }`}
        >
          governor={summary.governor_enabled ? "enabled" : "DISABLED"}
        </span>
        <span
          className={`rounded-full border px-3 py-1 text-xs font-medium ${
            summary.auto_execute_enabled
              ? "border-blue-200 bg-blue-50 text-blue-700"
              : "border-zinc-200 bg-zinc-50 text-zinc-500"
          }`}
        >
          auto_execute={summary.auto_execute_enabled ? "on" : "off"}
        </span>
      </div>

      <section className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
        {metricCards.map(([id, label, value]) => (
          <div
            data-testid={`governor-metric-${id}`}
            key={id}
            className="rounded-lg border border-zinc-200 bg-white p-4"
          >
            <div className="text-xs text-zinc-500">{label}</div>
            <div className="mt-2 text-2xl font-semibold">{value}</div>
          </div>
        ))}
      </section>

      <section>
        <div className="mb-3 text-sm font-semibold">Pending Confirmations</div>
        {pendingDecisions.length ? (
          <div className="space-y-3">
            {pendingDecisions.map((d) => (
              <DecisionCard key={d.decision_id} decision={d} onConfirmed={handleConfirmed} />
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-zinc-200 bg-white p-4 text-sm text-zinc-500">
            No pending decisions.
          </div>
        )}
      </section>

      {summary.recent_receipts.length > 0 ? (
        <section>
          <div className="mb-3 text-sm font-semibold">Recent Execution Receipts</div>
          <div className="space-y-2">
            {summary.recent_receipts.map((r) => (
              <div
                key={r.receipt_id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-zinc-200 bg-white px-4 py-3 text-sm"
              >
                <div>
                  <span className="font-medium">{r.action_type}</span>
                  <span className="ml-2 text-xs text-zinc-500">→ {r.target_id}</span>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge
                    label={r.outcome}
                    colorClass={
                      r.outcome === "succeeded"
                        ? "text-green-700 bg-green-50 border-green-200"
                        : r.outcome === "skipped_duplicate"
                        ? "text-zinc-600 bg-zinc-50 border-zinc-200"
                        : "text-red-700 bg-red-50 border-red-200"
                    }
                  />
                  <span className="text-xs text-zinc-400">{r.executed_at}</span>
                </div>
                {r.result_summary ? (
                  <div className="w-full text-xs text-zinc-500">{r.result_summary}</div>
                ) : null}
                {r.error ? (
                  <div className="w-full text-xs text-red-700">{r.error}</div>
                ) : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {Object.keys(summary.circuit_breaker_state).length > 0 ? (
        <section>
          <div className="mb-3 text-sm font-semibold">Circuit Breaker State</div>
          <div className="space-y-2">
            {Object.entries(summary.circuit_breaker_state).map(([key, count]) => (
              <div
                key={key}
                className="flex items-center justify-between rounded-lg border border-yellow-200 bg-yellow-50 px-4 py-2 text-sm"
              >
                <span className="font-medium text-yellow-800">{key}</span>
                <span className="text-xs text-yellow-700">consecutive failures: {count}</span>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
