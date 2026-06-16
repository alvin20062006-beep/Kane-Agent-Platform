"use client";

import Link from "next/link";

import { ProductNotice } from "@/components/product-notice";
import { PageTitle } from "@/components/page-title";
import { useT } from "@/lib/i18n/LocaleProvider";

type Report = {
  report_id: string;
  type: string;
  title: string;
  created_at: string;
  content: string;
  is_draft: boolean;
};

type AdvisorSummary = {
  generated_at: string;
  totals: Record<string, number>;
  pattern_summary: Array<{
    pattern_key: string;
    occurrence_count: number;
    last_seen_at: string | null;
    affected_targets: number;
    confidence: string;
  }>;
  policy_suggestion_summary: Array<{
    suggestion_id: string;
    title: string;
    status: string;
    confidence: string | null;
    occurrence_count: number;
    target_label: string | null;
    current_effective_mode: string | null;
    suggested_mode: string | null;
  }>;
};

export function ReportsClient({
  items,
  total,
  advisor,
  errorText,
}: {
  items: Report[] | null;
  total?: number;
  advisor: AdvisorSummary | null;
  errorText: string | null;
}) {
  const t = useT();
  return (
    <div className="space-y-6 p-6">
      <PageTitle title={t("reports.title")} subtitle={t("reports.subtitle")} />
      <ProductNotice note={t("reports.notice")} />

      {errorText ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {errorText}
        </div>
      ) : null}

      {advisor ? (
        <div data-testid="reports-advisor-summary" className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-semibold">Advisor Summary</div>
            <div className="text-xs text-zinc-500">
              open={advisor.totals.open ?? 0} / accepted={advisor.totals.accepted ?? 0} / dismissed={advisor.totals.dismissed ?? 0}
            </div>
          </div>
          {advisor.pattern_summary.length > 0 ? (
            <div className="mt-3">
              <div className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">Repeated Patterns</div>
              <div className="space-y-2">
                {advisor.pattern_summary.map((p) => (
                  <div key={p.pattern_key} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-zinc-100 bg-zinc-50 px-3 py-2 text-xs">
                    <span className="font-medium text-zinc-800">{p.pattern_key}</span>
                    <span className="text-zinc-500">
                      occurrences={p.occurrence_count} · targets={p.affected_targets} · confidence={p.confidence}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {advisor.policy_suggestion_summary.length > 0 ? (
            <div className="mt-3">
              <div className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">Top Policy Suggestions</div>
              <div className="space-y-2">
                {advisor.policy_suggestion_summary.map((p) => (
                  <div key={p.suggestion_id} className="rounded-md border border-zinc-100 bg-zinc-50 px-3 py-2 text-xs">
                    <div className="font-medium text-zinc-800">{p.title}</div>
                    {p.current_effective_mode && p.suggested_mode ? (
                      <div className="mt-1 text-zinc-500">
                        {p.target_label ?? p.suggestion_id}: {p.current_effective_mode} → {p.suggested_mode} · {p.status}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {advisor.pattern_summary.length === 0 && advisor.policy_suggestion_summary.length === 0 ? (
            <div className="mt-3 text-sm text-zinc-500">No patterns or policy suggestions have been generated yet.</div>
          ) : null}
        </div>
      ) : null}

      {items ? (
        <div className="space-y-3">
          {total && total > items.length ? (
            <div className="text-xs text-zinc-500">{`${items.length} / ${total}`}</div>
          ) : null}
          {items.map((report) => (
            <div key={report.report_id} className="rounded-lg border border-zinc-200 bg-white p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-semibold">{report.title}</div>
                  <div className="mt-1 text-xs text-zinc-500">
                    {report.report_id} • {report.type} • {t(report.is_draft ? "reports.kind_draft" : "reports.kind_persisted")}
                  </div>
                </div>
                <div className="text-xs text-zinc-500">{report.created_at}</div>
              </div>
              <div className="mt-3 whitespace-pre-wrap text-sm text-zinc-700">{report.content}</div>
              <div className="mt-4">
                <Link
                  href={`/reports/${encodeURIComponent(report.report_id)}`}
                  className="inline-block rounded-md border border-zinc-200 px-3 py-2 text-sm hover:bg-zinc-50"
                >
                  {t("reports.open")}
                </Link>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

