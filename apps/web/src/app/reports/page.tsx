import { apiGet } from "@/lib/api";
import type { ListResponse } from "@/lib/octopus-types";

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

export default async function ReportsPage() {
  let data: ListResponse<Report> | null = null;
  let advisorData: AdvisorSummary | null = null;
  let error: unknown = null;
  try {
    [data, { data: advisorData }] = await Promise.all([
      apiGet<ListResponse<Report>>("/reports"),
      apiGet<{ data: AdvisorSummary }>("/advisor"),
    ]);
  } catch (e) {
    error = e;
  }
  const errorText = error ? (error instanceof Error ? error.message : String(error)) : null;
  const { ReportsClient } = await import("./reports-client");
  return (
    <ReportsClient
      items={data?.items ?? null}
      total={data?.total ?? data?.items?.length ?? 0}
      advisor={advisorData}
      errorText={errorText}
    />
  );
}
