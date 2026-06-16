import type { ListResponse } from "@/lib/api";
import { apiGet } from "@/lib/api";
import type { AdvisorSuggestion } from "@/lib/octopus-types";

type ExecutionPolicy = {
  policy_id: string;
  scope: "global" | "agent" | "skill" | "account";
  target_id?: string | null;
  mode: "auto" | "notify" | "confirm";
  note?: string | null;
  is_draft: boolean;
};

export default async function PoliciesPage() {
  let data: ListResponse<ExecutionPolicy> | null = null;
  let advisorData: ListResponse<AdvisorSuggestion> | null = null;
  let error: unknown = null;

  try {
    [data, advisorData] = await Promise.all([
      apiGet<ListResponse<ExecutionPolicy>>("/policies"),
      apiGet<ListResponse<AdvisorSuggestion>>("/advisor/suggestions?suggestion_type=policy_draft_suggestion&status=open"),
    ]);
  } catch (e) {
    error = e;
  }

  const errorText = error ? (error instanceof Error ? error.message : String(error)) : null;
  const { PoliciesClient } = await import("./policies-client");
  return (
    <PoliciesClient
      items={data?.items ?? null}
      suggestions={advisorData?.items ?? []}
      errorText={errorText}
    />
  );
}
