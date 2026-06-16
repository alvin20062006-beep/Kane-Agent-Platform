import { apiGet } from "@/lib/api";
import type { ObserverSummary } from "@/lib/octopus-types";

import { ObserverClient } from "./observer-client";
import { ObserverLoadError } from "./observer-load-error";

export default async function ObserverPage() {
  let data: ObserverSummary | undefined;
  let loadError: unknown = null;
  try {
    const response = await apiGet<{ data: ObserverSummary }>("/observer");
    data = response.data;
  } catch (e) {
    loadError = e;
  }
  if (loadError) {
    return <ObserverLoadError error={loadError} />;
  }
  return <ObserverClient data={data!} />;
}
