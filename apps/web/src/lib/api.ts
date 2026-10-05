/** HTTP projections of the vNext FastAPI contract. No client-owned runtime state. */
export type TurnStatus = "running" | "waiting_user" | "finished" | "failed" | "interrupted";
export type Conversation = { conversation_id: string; title: string; bound_agent_id: string; focus_turn_id: string | null; created_at: string; updated_at: string };
export type Message = { message_id: string; conversation_id: string; turn_id: string | null; sender: "user" | "agent" | "system"; sender_id: string | null; reply_to: string | null; parent_id: string | null; content: string; kind: "normal" | "edit" | "retract"; target_message_id: string | null; created_at: string };
export type Turn = { turn_id: string; conversation_id: string; bound_agent_id: string; branch_id: string; title: string | null; status: TurnStatus; native_session_ref: string | null; last_event_at: string; interrupt_reason: string | null; partial_output: string | null; created_at: string; finished_at: string | null };
export type Agent = { agent_id: string; display_name?: string | null; status: string; supports_stream: boolean; supports_resume: boolean; supports_cancel: boolean; supports_approval: boolean; supports_parallel_sessions: boolean; max_parallel_sessions: number | null; branch_mode: "native" | "replay" | "unsupported"; steer_mode: "native" | "safe_boundary" | "follow_up_only"; auto_start: boolean | null };
export type AgentPairing = { agent_id: string; pairing_code: string; expires_in_seconds: number | null };
export type Permission = { request_id: string; title: string; created_at: number };
export type Activity = { event_id: string; event_type: string; created_at: string; payload: Record<string, string> };
export type TurnDetail = Turn & { pending_permissions: Permission[]; loop: { current_iteration: number; max_iterations: number | null; stop_requested: boolean } | null; events: Activity[] };
export type Decision = "allow-once" | "reject-once" | "cancelled";
export type SendBody = { content: string; turn_id?: string; reply_to_message_id?: string; loop_mode?: boolean; max_iterations?: number | null };

export function getApiBaseUrl() {
  return process.env.KANE_API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
}

export class ApiRequestError extends Error {
  constructor(public status: number, message: string) { super(message); this.name = "ApiRequestError"; }
}

async function responseError(response: Response): Promise<ApiRequestError> {
  const data = await response.json().catch(() => null);
  const detail = data?.detail;
  return new ApiRequestError(response.status, typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((item: { msg?: string }) => item.msg).join("; ") : `HTTP ${response.status}`);
}

const url = (path: string) => `/api/proxy/api/v1${path}`;
const id = encodeURIComponent;
const accessTokenKey = "kane.apiAccessToken";

export function setApiAccessToken(token: string) {
  sessionStorage.setItem(accessTokenKey, token.trim());
}

function requestHeaders(body = false): Headers {
  const headers = new Headers();
  if (body) headers.set("Content-Type", "application/json");
  const token = sessionStorage.getItem(accessTokenKey);
  if (token) headers.set("X-Api-Key", token);
  return headers;
}

async function request<T>(path: string, body?: unknown, signal?: AbortSignal, method?: string): Promise<T> {
  const response = await fetch(url(path), {
    method: method ?? (body === undefined ? "GET" : "POST"),
    headers: requestHeaders(body !== undefined),
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
    signal: signal ?? AbortSignal.timeout(30000),
  });
  if (!response.ok) throw await responseError(response);
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

export const api = {
  agents: (signal?: AbortSignal) => request<Agent[]>("/agents", undefined, signal),
  renameAgent: (aid: string, display_name: string) => request<{ agent_id: string; display_name: string }>(`/agents/${id(aid)}`, { display_name }, undefined, "PATCH"),
  disconnectAgent: (aid: string) => request<void>(`/agents/${id(aid)}/disconnect`, {}, undefined),
  deleteAgent: (aid: string) => request<void>(`/agents/${id(aid)}`, undefined, undefined, "DELETE"),
  createAgentPairing: (agent_id: string, display_name: string) => request<AgentPairing>("/agents/pairings", { agent_id, display_name }),
  activateKanaloa: () => request<Agent>("/agents/kanaloa/activate", {}, AbortSignal.timeout(45000)),
  deactivateKanaloa: () => request<void>("/agents/kanaloa/deactivate", {}),
  setKanaloaAutoStart: (auto_start: boolean) => request<Agent>("/agents/kanaloa/preferences", { auto_start }),
  saveKanaloaModelConfig: (config: { base_url: string; model: string; api_key: string }) => request<{ status: string; provider: string; model: string }>("/agents/kanaloa/model-config", config),
  conversations: (signal?: AbortSignal) => request<Conversation[]>("/conversations", undefined, signal),
  renameConversation: (cid: string, title: string) => request<Conversation>(`/conversations/${id(cid)}`, { title }, undefined, "PATCH"),
  deleteConversation: (cid: string) => request<void>(`/conversations/${id(cid)}`, undefined, undefined, "DELETE"),
  conversation: (cid: string, signal?: AbortSignal) => request<Conversation>(`/conversations/${id(cid)}`, undefined, signal),
  createConversation: (title: string, agent: string) => request<Conversation>("/conversations", { title, bound_agent_id: agent }),
  turns: (cid: string, signal?: AbortSignal) => request<Turn[]>(`/conversations/${id(cid)}/turns`, undefined, signal),
  turn: (tid: string, signal?: AbortSignal) => request<TurnDetail>(`/turns/${id(tid)}`, undefined, signal),
  messages: (cid: string, tid: string | null, signal?: AbortSignal) => request<Message[]>(`/conversations/${id(cid)}/messages${tid ? `?turn_id=${id(tid)}` : ""}`, undefined, signal),
  send: (cid: string, body: SendBody) => request<{ message: Message; turn: Turn }>(`/conversations/${id(cid)}/messages`, body),
  newTask: (cid: string, title: string, branchId?: string) => request<Turn>(`/conversations/${id(cid)}/turns`, { title, branch_id: branchId }),
  focus: (cid: string, tid: string) => request<{ focus_turn_id: string }>(`/conversations/${id(cid)}/focus`, { turn_id: tid }),
  branch: (cid: string, mid: string, name: string) => request<{ branch_id: string; initial_turn_id: string }>(`/conversations/${id(cid)}/branches`, { message_id: mid, name }),
  control: (tid: string, action: "cancel" | "resume" | "stop-loop") => request<Turn>(`/turns/${id(tid)}/${action}`, {}),
  permission: (tid: string, rid: string, decision: Decision) => request<{ status: string }>(`/turns/${id(tid)}/permissions/${id(rid)}/respond`, { decision }),
};

/** Read SSE frames, including frames split across transport chunks. Never replay. */
export async function streamTurn(tid: string, signal: AbortSignal, onEvent: (type: string, data: unknown) => void) {
  const headers = requestHeaders();
  headers.set("Accept", "text/event-stream");
  const response = await fetch(url(`/turns/${id(tid)}/stream`), { signal, cache: "no-store", headers });
  if (!response.ok) throw await responseError(response);
  if (!response.body || !response.headers.get("content-type")?.includes("text/event-stream")) throw new Error("Event stream unavailable");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let match: RegExpExecArray | null;
      while ((match = /\r?\n\r?\n/.exec(buffer))) {
        const frame = buffer.slice(0, match.index);
        buffer = buffer.slice(match.index + match[0].length);
        const lines = frame.split(/\r?\n/);
        const type = lines.find(line => line.startsWith("event:"))?.slice(6).trim() ?? "message";
        const data = lines.filter(line => line.startsWith("data:")).map(line => line.slice(5).trimStart()).join("\n");
        if (data) onEvent(type, JSON.parse(data));
      }
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
