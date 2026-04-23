import type { ListResponse } from "@/lib/api";
import { apiGet } from "@/lib/api";

type ExecutionPolicy = {
  policy_id: string;
  scope: "global" | "agent" | "skill" | "account";
  target_id?: string | null;
  mode: "auto" | "notify" | "confirm";
  note?: string | null;
  is_mock: boolean;
};

export default async function PoliciesPage() {
  let data: ListResponse<ExecutionPolicy> | null = null;
  let error: unknown = null;

  try {
    data = await apiGet<ListResponse<ExecutionPolicy>>("/policies");
  } catch (e) {
    error = e;
  }

  const errorText = error ? (error instanceof Error ? error.message : String(error)) : null;
  const { PoliciesClient } = await import("./policies-client");
  return <PoliciesClient items={data?.items ?? null} errorText={errorText} />;
}

