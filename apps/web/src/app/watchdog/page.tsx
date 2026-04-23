import { ApiError } from "@/components/api-error";
import { apiGet } from "@/lib/api";
import type { WatchdogStatus } from "@/lib/octopus-types";

import { WatchdogClient } from "./watchdog-client";

export default async function WatchdogPage() {
  try {
    const response = await apiGet<{ data: WatchdogStatus }>("/watchdog");

    return <WatchdogClient data={response.data} />;
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
}
