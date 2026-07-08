"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";

import { JsonCard } from "@/components/json-card";
import { apiGet, apiPost } from "@/lib/api";
import type {
  AggregatorDecision,
  ListResponse,
  MemoryCompilerCandidate,
  MemoryCompilerRun,
  ReferenceCandidate,
  RepairAttempt,
  Run,
  RunStep,
  VerifierResult,
} from "@/lib/octopus-types";

type RunAuditBundle = {
  steps: RunStep[];
  references: ReferenceCandidate[];
  aggregations: AggregatorDecision[];
  verifiers: VerifierResult[];
  repairs: RepairAttempt[];
};

type AuditState = {
  byRun: Record<string, RunAuditBundle>;
  compilerRuns: MemoryCompilerRun[];
  compilerCandidates: MemoryCompilerCandidate[];
};

const EMPTY_BUNDLE: RunAuditBundle = {
  steps: [],
  references: [],
  aggregations: [],
  verifiers: [],
  repairs: [],
};

function badgeClass(value: string) {
  if (["succeeded", "passed", "committed", "active", "allowed"].includes(value)) {
    return "border-emerald-200 bg-emerald-50 text-emerald-700";
  }
  if (["failed", "blocked", "needs_user_confirmation"].includes(value)) {
    return "border-rose-200 bg-rose-50 text-rose-700";
  }
  if (["running", "proposed", "candidate", "pending"].includes(value)) {
    return "border-amber-200 bg-amber-50 text-amber-700";
  }
  return "border-zinc-200 bg-zinc-50 text-zinc-600";
}

function Badge({ children }: { children: string | number | boolean | null | undefined }) {
  const value = String(children ?? "none");
  return (
    <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium ${badgeClass(value)}`}>
      {value}
    </span>
  );
}

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-zinc-900">{title}</div>
          {description ? <p className="mt-1 text-xs text-zinc-500">{description}</p> : null}
        </div>
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Empty({ label }: { label: string }) {
  return <div className="rounded-md border border-dashed border-zinc-200 p-3 text-sm text-zinc-500">{label}</div>;
}

function IdLine({ label, value }: { label: string; value?: string | number | null }) {
  return (
    <div className="min-w-0 text-xs">
      <span className="text-zinc-500">{label}: </span>
      <span className="break-all font-mono text-zinc-700">{value ?? "none"}</span>
    </div>
  );
}

function asArray<T>(payload: ListResponse<T> | { items?: T[] }): T[] {
  return Array.isArray(payload.items) ? payload.items : [];
}

async function readList<T>(path: string): Promise<T[]> {
  try {
    return asArray(await apiGet<ListResponse<T>>(path));
  } catch {
    return [];
  }
}

export function ExecutionAuditPanel({ taskId, runs }: { taskId: string; runs: Run[] }) {
  const [audit, setAudit] = useState<AuditState>({
    byRun: {},
    compilerRuns: [],
    compilerCandidates: [],
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const [committingId, setCommittingId] = useState<string | null>(null);

  const runIds = useMemo(() => runs.map((run) => run.run_id), [runs]);
  const selectedCandidate = audit.compilerCandidates.find((candidate) => candidate.candidate_id === selectedCandidateId);

  const load = async () => {
    if (!runIds.length) return;
    setLoading(true);
    setError(null);
    try {
      const entries = await Promise.all(
        runIds.map(async (runId) => {
          const [steps, references, aggregations, verifiers, repairs] = await Promise.all([
            readList<RunStep>(`/runs/${encodeURIComponent(runId)}/steps`),
            readList<ReferenceCandidate>(`/runs/${encodeURIComponent(runId)}/reference-candidates`),
            readList<AggregatorDecision>(`/runs/${encodeURIComponent(runId)}/reference-aggregations`),
            readList<VerifierResult>(`/runs/${encodeURIComponent(runId)}/verifier-results`),
            readList<RepairAttempt>(`/runs/${encodeURIComponent(runId)}/repair-attempts`),
          ]);
          return [runId, { steps, references, aggregations, verifiers, repairs }] as const;
        })
      );
      const [compilerRuns, compilerCandidates] = await Promise.all([
        readList<MemoryCompilerRun>(`/memory/compiler/runs?task_id=${encodeURIComponent(taskId)}`),
        readList<MemoryCompilerCandidate>(`/memory/compiler/candidates?task_id=${encodeURIComponent(taskId)}`),
      ]);
      setAudit({
        byRun: Object.fromEntries(entries),
        compilerRuns,
        compilerCandidates,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [taskId, runIds.join("|")]);

  const commitCandidate = async (candidate: MemoryCompilerCandidate) => {
    const ok = confirm(
      [
        "Commit this compiler candidate to the append-only Memory Ledger?",
        "This is a manual AI memory commit. It will append a MemoryEvent and update snapshot/index through ledger projection.",
        "User delete/rewrite/purge controls remain available after commit.",
      ].join("\n\n")
    );
    if (!ok) return;
    setCommittingId(candidate.candidate_id);
    try {
      await apiPost(`/memory/compiler/candidates/${encodeURIComponent(candidate.candidate_id)}/commit`, {
        metadata: { ui_confirmed: true, source: "task_execution_audit_panel" },
      });
      await load();
      setSelectedCandidateId(candidate.candidate_id);
    } finally {
      setCommittingId(null);
    }
  };

  return (
    <div className="space-y-4" data-testid="task-execution-audit-panel">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-zinc-900">Execution Audit</h2>
          <p className="mt-1 text-xs text-zinc-500">
            Inspect RunStep timeline, reference review, verifier, repair, and compiler records. This panel does not execute repairs.
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
        >
          {loading ? "Refreshing" : "Refresh audit"}
        </button>
      </div>

      {error ? <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div> : null}
      {!runIds.length ? <Empty label="No runs are available for this task yet." /> : null}

      {runs.map((run) => {
        const bundle = audit.byRun[run.run_id] ?? EMPTY_BUNDLE;
        return (
          <div key={run.run_id} className="space-y-4 rounded-lg border border-zinc-200 bg-zinc-50 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-zinc-900">{run.run_id}</div>
                <div className="mt-1 text-xs text-zinc-500">
                  {run.integration_path ?? "unknown path"} / finished {run.finished_at ?? "none"}
                </div>
              </div>
              <Badge>{run.status}</Badge>
            </div>

            <Section title="Run Timeline" description="RunStep is the execution timeline, with references to evidence records.">
              {bundle.steps.length ? (
                <div className="space-y-3">
                  {bundle.steps.map((step) => (
                    <div key={step.run_step_id} className="rounded-md border border-zinc-200 bg-white p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="text-sm font-medium">
                          {step.sequence}. {step.step_type} {step.title ? `- ${step.title}` : ""}
                        </div>
                        <Badge>{step.status}</Badge>
                      </div>
                      <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
                        <IdLine label="retry_count" value={step.retry_count} />
                        <IdLine label="latest_failure_type" value={step.latest_failure_type} />
                        <IdLine label="verification_ref" value={step.verification_ref} />
                        <IdLine label="repair_ref" value={step.repair_ref} />
                        <IdLine label="decision_id" value={step.decision_id} />
                        <IdLine label="failure_id" value={step.failure_id} />
                        <IdLine label="skill_id" value={step.skill_id} />
                        <IdLine label="output_ref" value={step.output_ref} />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty label="No RunStep records for this run." />
              )}
            </Section>

            <section className="grid gap-4 xl:grid-cols-2">
              <Section title="Reference / Aggregator Panel">
                <div className="space-y-4">
                  <div>
                    <div className="text-xs font-medium text-zinc-600">Reference candidates</div>
                    <div className="mt-2 space-y-2">
                      {bundle.references.length ? (
                        bundle.references.map((candidate) => (
                          <div key={candidate.candidate_id} className="rounded-md border border-zinc-200 bg-white p-3 text-sm">
                            <div className="flex flex-wrap justify-between gap-2">
                              <span className="font-medium">{candidate.agent_role}</span>
                              <Badge>{candidate.status}</Badge>
                            </div>
                            <p className="mt-2 text-zinc-700">{candidate.summary}</p>
                            <div className="mt-2 text-xs text-zinc-500">confidence {candidate.confidence}</div>
                          </div>
                        ))
                      ) : (
                        <Empty label="No reference candidates." />
                      )}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs font-medium text-zinc-600">Aggregator decisions</div>
                    <div className="mt-2 space-y-2">
                      {bundle.aggregations.length ? (
                        bundle.aggregations.map((decision) => (
                          <div key={decision.aggregation_id} className="rounded-md border border-zinc-200 bg-white p-3 text-sm">
                            <div className="flex flex-wrap justify-between gap-2">
                              <span className="font-medium">confidence {decision.confidence}</span>
                              <Badge>{decision.requires_user_confirmation ? "needs_confirmation" : "recorded"}</Badge>
                            </div>
                            <p className="mt-2 text-zinc-700">{decision.consensus}</p>
                            <div className="mt-3 grid gap-3 md:grid-cols-2">
                              <div>
                                <div className="text-xs text-zinc-500">selected_plan</div>
                                <ul className="mt-1 list-disc space-y-1 pl-4 text-xs text-zinc-700">
                                  {decision.selected_plan.map((item) => (
                                    <li key={item}>{item}</li>
                                  ))}
                                </ul>
                              </div>
                              <div>
                                <div className="text-xs text-zinc-500">conflicts</div>
                                <ul className="mt-1 list-disc space-y-1 pl-4 text-xs text-zinc-700">
                                  {decision.conflicts.length ? decision.conflicts.map((item) => <li key={item}>{item}</li>) : <li>none</li>}
                                </ul>
                              </div>
                            </div>
                          </div>
                        ))
                      ) : (
                        <Empty label="No aggregator decisions." />
                      )}
                    </div>
                  </div>
                </div>
              </Section>

              <Section title="Verifier Panel">
                <div className="space-y-2">
                  {bundle.verifiers.length ? (
                    bundle.verifiers.map((result) => (
                      <div key={result.result_id} className="rounded-md border border-zinc-200 bg-white p-3 text-sm">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="font-medium">{result.verifier_type}</div>
                          <div className="flex gap-2">
                            <Badge>{result.status}</Badge>
                            <Badge>{result.passed ? "passed" : "not_passed"}</Badge>
                          </div>
                        </div>
                        {result.findings.length ? (
                          <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-zinc-700">
                            {result.findings.map((item) => (
                              <li key={item}>{item}</li>
                            ))}
                          </ul>
                        ) : null}
                        {result.output_summary ? <p className="mt-2 text-xs text-zinc-600">{result.output_summary}</p> : null}
                        {result.error_summary ? <p className="mt-2 text-xs text-rose-700">{result.error_summary}</p> : null}
                      </div>
                    ))
                  ) : (
                    <Empty label="No verifier results." />
                  )}
                </div>
              </Section>
            </section>

            <Section title="Repair Panel" description="Repair attempts are records only here; this UI does not execute repair actions.">
              {bundle.repairs.length ? (
                <div className="grid gap-3 md:grid-cols-2">
                  {bundle.repairs.map((attempt) => (
                    <div key={attempt.repair_attempt_id} className="rounded-md border border-zinc-200 bg-white p-3 text-sm">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="font-medium">
                          {attempt.attempt_index}. {attempt.attempt_kind}
                        </div>
                        <Badge>{attempt.status}</Badge>
                      </div>
                      <div className="mt-3 grid gap-2">
                        <IdLine label="failure_type" value={attempt.failure_type} />
                        <IdLine label="repair_action" value={attempt.repair_action} />
                        <IdLine label="needs_user_confirmation" value={String(attempt.needs_user_confirmation)} />
                        <IdLine label="safety_status" value={attempt.safety_status} />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty label="No repair attempts." />
              )}
            </Section>
          </div>
        );
      })}

      <Section
        title="Memory Compiler Panel"
        description="Compiler runs are dry-run audit records. Candidates become MemoryEvents only after manual commit."
      >
        <div className="grid gap-4 xl:grid-cols-2">
          <div>
            <div className="text-xs font-medium text-zinc-600">Compiler runs</div>
            <div className="mt-2 space-y-2">
              {audit.compilerRuns.length ? (
                audit.compilerRuns.map((run) => (
                  <div key={run.compiler_run_id} className="rounded-md border border-zinc-200 p-3 text-sm">
                    <div className="flex flex-wrap justify-between gap-2">
                      <span className="break-all font-mono text-xs">{run.compiler_run_id}</span>
                      <Badge>{run.dry_run ? "dry_run" : "not_dry_run"}</Badge>
                    </div>
                    <div className="mt-2 grid gap-2 text-xs text-zinc-600 md:grid-cols-2">
                      <div>policy: {run.policy_name}</div>
                      <div>created: {run.candidates_created}</div>
                      <div>committed: {run.candidates_committed}</div>
                      <div>finished: {run.finished_at}</div>
                    </div>
                  </div>
                ))
              ) : (
                <Empty label="No compiler runs for this task." />
              )}
            </div>
          </div>
          <div>
            <div className="text-xs font-medium text-zinc-600">Compiler candidates</div>
            <div className="mt-2 space-y-2">
              {audit.compilerCandidates.length ? (
                audit.compilerCandidates.map((candidate) => (
                  <div key={candidate.candidate_id} className="rounded-md border border-zinc-200 p-3 text-sm">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <button
                        type="button"
                        onClick={() => setSelectedCandidateId(candidate.candidate_id)}
                        className="break-all text-left font-mono text-xs text-sky-700 underline"
                      >
                        {candidate.candidate_id}
                      </button>
                      <Badge>{candidate.status}</Badge>
                    </div>
                    <div className="mt-2 text-xs text-zinc-600">{candidate.candidate_type}</div>
                    <div className="mt-1 break-all text-xs text-zinc-500">{candidate.subject_key}</div>
                    {candidate.status === "proposed" ? (
                      <button
                        type="button"
                        disabled={committingId === candidate.candidate_id}
                        onClick={() => commitCandidate(candidate)}
                        className="mt-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-900 hover:bg-amber-100 disabled:opacity-50"
                      >
                        {committingId === candidate.candidate_id ? "Committing" : "Manual commit"}
                      </button>
                    ) : null}
                  </div>
                ))
              ) : (
                <Empty label="No compiler candidates for this task." />
              )}
            </div>
          </div>
        </div>
        {selectedCandidate ? (
          <div className="mt-4">
            <div className="mb-2 text-xs font-medium text-zinc-600">Candidate details</div>
            <JsonCard data={selectedCandidate} />
          </div>
        ) : null}
      </Section>
    </div>
  );
}
