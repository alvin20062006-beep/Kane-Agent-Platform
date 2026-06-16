"use client";

import { useState } from "react";

import { ProductNotice } from "@/components/product-notice";
import { PageTitle } from "@/components/page-title";
import { apiPost } from "@/lib/api";
import { useT } from "@/lib/i18n/LocaleProvider";
import type { AdvisorSuggestion, WatchdogEvent, WatchdogStatus } from "@/lib/octopus-types";

function issueKey(event: WatchdogEvent) {
  return `${event.task_id ?? "platform"}::${event.issue_class ?? event.type}::${event.normalized_issue_signature ?? "none"}`;
}

export function WatchdogClient({ data, suggestions }: { data: WatchdogStatus; suggestions: AdvisorSuggestion[] }) {
  const t = useT();
  const { summary, events, recovery_hints: recoveryHints } = data;
  const [latestIssues, setLatestIssues] = useState<WatchdogEvent[]>(data.latest_issues ?? []);
  const [busyEventId, setBusyEventId] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const summaryCards: Array<{ id: string; label: string; value: string | number }> = [
    { id: "running-tasks", label: t("watchdog.running_tasks"), value: summary.running_tasks },
    { id: "stalled-tasks", label: t("watchdog.stalled_tasks"), value: summary.stalled_tasks },
    { id: "failed-runs-24h", label: t("watchdog.failed_runs_24h"), value: summary.failed_tasks_recent },
    { id: "waiting-handoffs", label: t("watchdog.waiting_handoffs"), value: summary.waiting_handoffs },
    { id: "open-issues", label: t("watchdog.open_issues"), value: summary.open_issues },
    { id: "escalated-issues", label: t("watchdog.escalated_issues"), value: summary.escalated_issues },
    { id: "offline-agents", label: t("watchdog.offline_agents"), value: summary.offline_agents },
    { id: "degraded-agents", label: t("watchdog.degraded_agents"), value: summary.degraded_agents },
    { id: "bridge-reachable", label: t("watchdog.bridge_reachable"), value: String(summary.bridge_reachable) },
    { id: "last-run", label: t("watchdog.last_run"), value: summary.last_run_finished_at ?? t("dashboard.none") },
  ];

  const mutateIssueState = async (eventId: string, action: "acknowledge" | "resolve") => {
    setBusyEventId(eventId);
    setActionMessage(null);
    try {
      const response = await apiPost<{ data: WatchdogEvent }>(`/escalations/${eventId}/${action}`, {});
      setLatestIssues((current) =>
        [...current.filter((item) => issueKey(item) !== issueKey(response.data) && item.event_id !== eventId), response.data].sort((left, right) =>
          (right.last_seen_at ?? right.created_at).localeCompare(left.last_seen_at ?? left.created_at)
        )
      );
      setActionMessage(
        action === "acknowledge"
          ? `${t("watchdog.ack_ok")}: ${response.data.issue_class ?? response.data.type}`
          : `${t("watchdog.resolve_ok")}: ${response.data.issue_class ?? response.data.type}`
      );
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusyEventId(null);
    }
  };

  const actionableIssues = latestIssues.filter((event) => ["escalated", "processing"].includes(event.issue_status ?? ""));
  const issueSuggestions = suggestions.filter((suggestion) =>
    suggestion.suggestion_type === "recovery_suggestion" &&
    ["task", "watchdog", "bridge", "platform"].includes(suggestion.target_type)
  );

  return (
    <div className="space-y-6 p-6">
      <PageTitle title={t("watchdog.title")} subtitle={t("watchdog.subtitle")} />

      <ProductNotice note={t("watchdog.notice")} />

      <section className="grid gap-4 md:grid-cols-3 xl:grid-cols-4">
        {summaryCards.map((card) => (
          <div
            key={card.id}
            data-testid={`watchdog-summary-${card.id}`}
            className="rounded-lg border border-zinc-200 bg-white p-4"
          >
            <div className="text-xs text-zinc-600">{card.label}</div>
            <div className="mt-2 text-sm font-semibold">{card.value}</div>
          </div>
        ))}
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <div data-testid="watchdog-events-card" className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-sm font-semibold">{t("watchdog.events")}</div>
          <div className="mt-3 space-y-3">
            {events.map((event) => (
              <div key={event.event_id} className="rounded-md border border-zinc-200 p-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="font-medium">
                    {event.type} / {event.severity}
                  </div>
                  <div className="text-xs text-zinc-500">{event.created_at}</div>
                </div>
                {event.message ? <div className="mt-2 text-sm text-zinc-700">{event.message}</div> : null}
                {event.recovery_hint ? (
                  <div className="mt-2 text-xs text-zinc-500">
                    {t("watchdog.recovery")}: {event.recovery_hint}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>

        <div data-testid="watchdog-recovery-hints" className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-sm font-semibold">{t("watchdog.recovery_hints")}</div>
          <div className="mt-3 space-y-2">
            {recoveryHints.map((hint) => (
              <div key={hint} className="rounded-md border border-zinc-200 px-3 py-2 text-sm">
                {hint}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section data-testid="watchdog-escalations-card" className="rounded-lg border border-zinc-200 bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-sm font-semibold">Escalations</div>
          {actionMessage ? <div className="text-xs text-zinc-500">{actionMessage}</div> : null}
        </div>
        <div className="mt-3 space-y-3">
          {actionableIssues.length ? (
            actionableIssues.map((event) => (
              <div key={event.event_id} className="rounded-md border border-zinc-200 p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="font-medium">{event.issue_class ?? event.type}</div>
                  <div className="text-xs text-zinc-500">{event.last_seen_at ?? event.created_at}</div>
                </div>
                {event.message ? <div className="mt-2 text-zinc-700">{event.message}</div> : null}
                <div className="mt-2 text-xs text-zinc-500">
                  suggested_action={event.suggested_action ?? "n/a"} / task={event.task_id ?? "platform"} /
                  occurrences={event.occurrence_count ?? 1}
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    data-testid={`escalation-ack-${event.event_id}`}
                    type="button"
                    disabled={busyEventId === event.event_id || event.issue_status === "processing"}
                    onClick={() => mutateIssueState(event.event_id, "acknowledge")}
                    className="rounded-md border border-zinc-200 px-3 py-1.5 text-xs font-medium text-zinc-800 disabled:opacity-50"
                  >
                    Acknowledge
                  </button>
                  <button
                    data-testid={`escalation-resolve-${event.event_id}`}
                    type="button"
                    disabled={busyEventId === event.event_id}
                    onClick={() => mutateIssueState(event.event_id, "resolve")}
                    className="rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
                  >
                    Resolve
                  </button>
                </div>
              </div>
            ))
          ) : (
            <div className="text-sm text-zinc-500">No escalated issues right now.</div>
          )}
        </div>
      </section>

      <section data-testid="watchdog-issue-state-card" className="rounded-lg border border-zinc-200 bg-white p-4">
        <div className="text-sm font-semibold">Issue state</div>
        <div className="mt-3 space-y-3">
          {latestIssues.length ? (
            latestIssues.map((event) => (
              <div key={event.event_id} className="rounded-md border border-zinc-200 p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="font-medium">{event.issue_class ?? event.type}</div>
                  <div className="text-xs text-zinc-500">{event.last_seen_at ?? event.created_at}</div>
                </div>
                <div className="mt-2 flex flex-wrap gap-2 text-xs text-zinc-500">
                  <span className="rounded-full border border-zinc-200 px-2 py-1">
                    status={event.issue_status ?? "open"}
                  </span>
                  <span className="rounded-full border border-zinc-200 px-2 py-1">
                    source={event.source ?? "watchdog"}
                  </span>
                  <span className="rounded-full border border-zinc-200 px-2 py-1">
                    task={event.task_id ?? "platform"}
                  </span>
                  <span className="rounded-full border border-zinc-200 px-2 py-1">
                    occurrences={event.occurrence_count ?? 1}
                  </span>
                </div>
                {event.message ? <div className="mt-2 text-zinc-700">{event.message}</div> : null}
              </div>
            ))
          ) : (
            <div className="text-sm text-zinc-500">No active issue state rows right now.</div>
          )}
        </div>
      </section>

      <section data-testid="watchdog-advisor-card" className="rounded-lg border border-zinc-200 bg-white p-4">
        <div className="text-sm font-semibold">Issue Suggestions</div>
        <div className="mt-3 space-y-3">
          {issueSuggestions.length ? (
            issueSuggestions.map((suggestion) => (
              <div key={suggestion.suggestion_id} className="rounded-md border border-zinc-200 p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="font-medium">{suggestion.title}</div>
                  <div className="text-xs text-zinc-500">
                    {suggestion.severity} / {suggestion.status} / confidence={suggestion.confidence ?? "low"}
                  </div>
                </div>
                <div className="mt-2 text-zinc-700">{suggestion.summary}</div>
                <div className="mt-2 flex flex-wrap gap-2 text-xs text-zinc-500">
                  <span className="rounded-full border border-zinc-200 px-2 py-1">
                    occurrences={suggestion.occurrence_count ?? 1}
                  </span>
                  <span className="rounded-full border border-zinc-200 px-2 py-1">
                    affected_targets={suggestion.affected_targets ?? 1}
                  </span>
                </div>
                <div className="mt-2 text-xs text-zinc-500">next: {suggestion.recommended_action}</div>
              </div>
            ))
          ) : (
            <div className="text-sm text-zinc-500">No issue suggestions have been generated yet.</div>
          )}
        </div>
      </section>
    </div>
  );
}
