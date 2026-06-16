import { ApiError } from "@/components/api-error";
import { apiGet } from "@/lib/api";
import type { ListResponse } from "@/lib/octopus-types";

import { NotificationsLayoutClient } from "./notifications-layout-client";
import { NotificationsChannelsClient, type NotificationChannelRow } from "./notifications-channels-client";

export default async function NotificationsPage() {
  let data: ListResponse<NotificationChannelRow> | null = null;
  let error: unknown = null;
  try {
    data = await apiGet<ListResponse<NotificationChannelRow>>("/notifications/channels");
  } catch (e) {
    error = e;
  }

  return (
    <NotificationsLayoutClient>
      {error ? <ApiError error={error} /> : null}
      {data ? (
        <NotificationsChannelsClient
          initial={{
            ...data,
            items: data.items as NotificationChannelRow[],
          }}
        />
      ) : null}
    </NotificationsLayoutClient>
  );
}
