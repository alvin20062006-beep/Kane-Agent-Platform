"use client";

import { useState } from "react";

import { getApiBaseUrl } from "@/lib/api";
import { useT } from "@/lib/i18n/LocaleProvider";
import type { ListResponse } from "@/lib/octopus-types";

export type NotificationChannelRow = {
  channel_id: string;
  enabled: boolean;
  name?: string | null;
  webhook_url?: string | null;
  created_at: string;
  updated_at?: string | null;
};

type Props = {
  initial: ListResponse<NotificationChannelRow>;
};

export function NotificationsChannelsClient({ initial }: Props) {
  const t = useT();
  const [items, setItems] = useState(initial.items);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  async function toggleEnabled(ch: NotificationChannelRow, next: boolean) {
    setError(null);
    setOkMsg(null);
    setBusyId(ch.channel_id);
    const base = getApiBaseUrl();
    const url = `${base}/notifications/channels`;
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          channel_id: ch.channel_id,
          enabled: next,
          name: ch.name ?? undefined,
          webhook_url: ch.webhook_url ?? undefined,
        }),
      });
      if (!res.ok) {
        const errBody = await res.text();
        throw new Error(`${res.status} ${errBody.slice(0, 400)}`);
      }
      const body = (await res.json()) as { data: NotificationChannelRow };
      setItems((prev) =>
        prev.map((x) => (x.channel_id === body.data.channel_id ? body.data : x))
      );
      setOkMsg(
        t("notif.channels.updated").replace("{id}", ch.channel_id).replace("{enabled}", String(next))
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  if (!items.length) {
    return <p className="text-sm text-zinc-600">{t("notif.channels.empty")}</p>;
  }

  return (
    <div className="space-y-4">
      {error ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
      ) : null}
      {okMsg ? (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
          {okMsg}
        </div>
      ) : null}
      <ul className="space-y-3">
        {items.map((ch) => (
          <li
            key={ch.channel_id}
            className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="font-medium text-zinc-900">{ch.channel_id}</div>
                <div className="mt-1 text-sm text-zinc-600">
                  {ch.name || "—"} · webhook: {ch.webhook_url || t("notif.webhook.unconfigured")}
                </div>
                <div className="mt-1 text-xs text-zinc-400">
                  created {ch.created_at}
                  {ch.updated_at ? ` · updated ${ch.updated_at}` : ""}
                </div>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <span className="text-zinc-600">{t("notif.label.enabled")}</span>
                <input
                  type="checkbox"
                  checked={ch.enabled}
                  disabled={busyId === ch.channel_id}
                  onChange={(ev) => void toggleEnabled(ch, ev.target.checked)}
                  className="h-4 w-4 rounded border-zinc-300"
                />
              </label>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
