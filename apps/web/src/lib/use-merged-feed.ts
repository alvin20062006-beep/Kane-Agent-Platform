"use client";

import { useCallback, useState } from "react";

import { apiGet } from "@/lib/api";
import type { Conversation, ListResponse, TaskEvent } from "@/lib/octopus-types";

export type FeedItem = {
  id: string;
  kind: "task" | "conversation";
  at: string;
  title: string;
  detail?: string;
};

type Options = {
  conversationLabel?: string;
  conversationLimit?: number;
  maxItems?: number;
};

export function useMergedFeed(
  _taskEvents: TaskEvent[],
  options: Options = {},
) {
  const { conversationLabel = "conversation", conversationLimit = 5, maxItems = 30 } = options;
  const [feed, setFeed] = useState<FeedItem[]>([]);

  const rebuild = useCallback(
    async (events: TaskEvent[]) => {
      const items: FeedItem[] = events.map((event) => ({
        id: event.event_id,
        kind: "task" as const,
        at: event.created_at,
        title: event.type,
        detail: event.message ?? undefined,
      }));
      try {
        const convs = await apiGet<ListResponse<Conversation>>(
          `/conversations?limit=${conversationLimit}`,
        );
        for (const conv of convs.items) {
          items.push({
            id: `conv-${conv.conversation_id}`,
            kind: "conversation",
            at: conv.last_message_at ?? conv.updated_at ?? conv.created_at,
            title: conv.title,
            detail: conversationLabel,
          });
        }
      } catch {
        // ignore
      }
      items.sort((a, b) => b.at.localeCompare(a.at));
      setFeed(items.slice(0, maxItems));
    },
    [conversationLabel, conversationLimit, maxItems],
  );

  return { feed, rebuild };
}
