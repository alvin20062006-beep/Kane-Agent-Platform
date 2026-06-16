import { ApiError } from "@/components/api-error";
import { apiGet } from "@/lib/api";
import type { GovernorSummary } from "@/lib/octopus-types";

import { GovernorClient } from "./governor-client";

export default async function GovernorPage() {
  let response: { data: GovernorSummary };
  try {
    response = await apiGet<{ data: GovernorSummary }>("/governor");
  } catch (error) {
    return (
      <div className="space-y-6 p-6">
        <div className="space-y-1">
          <div className="text-xl font-semibold tracking-tight">Governor</div>
          <div className="text-sm text-zinc-600">Controlled execution layer</div>
        </div>
        <ApiError error={error} />
      </div>
    );
  }

  return <GovernorClient summary={response.data} />;
}
