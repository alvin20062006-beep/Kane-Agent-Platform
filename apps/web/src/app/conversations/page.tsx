import { apiGet } from "@/lib/api";
import type {
  Agent,
  Conversation,
  ListResponse,
} from "@/lib/octopus-types";

import { ConversationsClient } from "./conversations-client";
import { ConversationsLoadError } from "./conversations-load-error";

export default async function ConversationsPage() {
  try {
    const [conversations, agents] = await Promise.all([
      apiGet<ListResponse<Conversation>>("/conversations"),
      apiGet<ListResponse<Agent>>("/agents"),
    ]);

    return (
      <div className="flex h-full min-h-0">
        <ConversationsClient
          initialConversations={conversations.items}
          agents={agents.items}
        />
      </div>
    );
  } catch (error) {
    return <ConversationsLoadError error={error} />;
  }
}
