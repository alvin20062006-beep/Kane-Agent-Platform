import { ApiError } from "@/components/api-error";
import { apiGet } from "@/lib/api";
import type { AdvisorSuggestion, WatchdogStatus } from "@/lib/octopus-types";

import { WatchdogClient } from "./watchdog-client";

export default async function WatchdogPage() {
  let response: { data: WatchdogStatus };
  let advisor: { items: AdvisorSuggestion[] };
  try {
    [response, advisor] = await Promise.all([
      apiGet<{ data: WatchdogStatus }>("/watchdog"),
      apiGet<{ items: AdvisorSuggestion[] }>("/advisor/suggestions?status=open"),
    ]);
  } catch (error) {
    return (
      <div className="space-y-6 p-6">
        <div className="space-y-1">
          <div className="text-xl font-semibold tracking-tight">Watchdog</div>
          <div className="text-sm text-zinc-600">Failure and recovery visibility</div>
        </div>
        <ApiError error={error} />
      </div>
    );
  }

  return <WatchdogClient data={response.data} suggestions={advisor.items} />;
}
