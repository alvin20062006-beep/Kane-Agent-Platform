"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";

import { apiDelete, apiGet, apiPatch, apiPost } from "@/lib/api";
import { useLocale, useT } from "@/lib/i18n/LocaleProvider";
import { formatRelativeTime } from "@/lib/i18n/relative-time";
import { listModesFor, modeLabelKey, type ExecutionMode } from "@/lib/modes";
import type {
  Agent,
  ApiProfile,
  Conversation,
  ConversationMessage,
  ListResponse,
} from "@/lib/octopus-types";

// ---- minimal shapes for skill / credential drop-downs ----
type SkillLite = {
  skill_id: string;
  name: string;
  enabled?: boolean;
  skill_scope?: "platform" | "agent_private" | null;
};

type CredentialLite = {
  credential_id: string;
  provider?: string | null;
  name?: string | null;
  masked_value?: string | null;
};

type Props = {
  initialConversations: Conversation[];
  agents: Agent[];
};

type TaskEventVirtualMessage = {
  message_id: string;
  conversation_id: string;
  role: "system";
  kind: "task_event";
  content: string;
  created_at: string;
  task_event_type: string;
  task_id: string;
};

type ConversationDetail = {
  conversation: Conversation;
  messages: ConversationMessage[];
  agent?: Agent | null;
  task_events?: TaskEventVirtualMessage[];
  promoted_task_id?: string | null;
};

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

// ---------------------- RowMenu primitive ----------------------

type MenuItem =
  | {
      label: string;
      onClick: () => void;
      danger?: boolean;
      disabled?: boolean;
      hint?: string;
    }
  | { separator: true };

function RowMenu({
  items,
  align = "right",
  triggerClassName,
  trigger,
  testid,
  ariaLabel,
}: {
  items: MenuItem[];
  align?: "left" | "right";
  triggerClassName?: string;
  trigger?: React.ReactNode;
  testid?: string;
  ariaLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onEsc = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          e.preventDefault();
          setOpen((v) => !v);
        }}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={ariaLabel ?? "More actions"}
        data-testid={testid}
        className={cx(
          "inline-flex h-7 w-7 items-center justify-center rounded hover:bg-zinc-200/70 text-zinc-500 hover:text-zinc-900",
          triggerClassName
        )}
      >
        {trigger ?? (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
            <circle cx="5" cy="12" r="1.8" />
            <circle cx="12" cy="12" r="1.8" />
            <circle cx="19" cy="12" r="1.8" />
          </svg>
        )}
      </button>
      {open && (
        <div
          role="menu"
          className={cx(
            "absolute z-20 mt-1 w-44 rounded-md border border-zinc-200 bg-white py-1 text-sm shadow-lg",
            align === "right" ? "right-0" : "left-0"
          )}
          onClick={(e) => e.stopPropagation()}
        >
          {items.map((item, idx) => {
            if ("separator" in item) {
              return <div key={idx} className="my-1 h-px bg-zinc-100" />;
            }
            return (
              <button
                key={idx}
                role="menuitem"
                type="button"
                disabled={item.disabled}
                title={item.hint}
                onClick={() => {
                  setOpen(false);
                  item.onClick();
                }}
                className={cx(
                  "flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors",
                  item.disabled
                    ? "cursor-not-allowed text-zinc-400"
                    : item.danger
                    ? "text-red-600 hover:bg-red-50"
                    : "text-zinc-700 hover:bg-zinc-100"
                )}
              >
                {item.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---------------------- main client ----------------------

export function ConversationsClient({ initialConversations, agents }: Props) {
  const t = useT();
  const { locale } = useLocale();
  const fmtDate = useCallback(
    (iso?: string | null) => formatRelativeTime(iso, t, locale),
    [t, locale]
  );
  const [conversations, setConversations] = useState(initialConversations);
  const [selectedId, setSelectedId] = useState<string | null>(
    initialConversations[0]?.conversation_id ?? null
  );
  const [detail, setDetail] = useState<ConversationDetail | null>(null);

  // composer state
  const [content, setContent] = useState("");
  const [remember, setRemember] = useState(false);
  const [busy, setBusy] = useState(false);
  const [errorText, setErrorText] = useState("");
  const [lastCandidateId, setLastCandidateId] = useState<string | null>(null);

  // operator + mode
  const [operatorAgentId, setOperatorAgentId] = useState<string>(
    initialConversations[0]?.agent_id ?? ""
  );
  const [executionMode, setExecutionMode] = useState<ExecutionMode>(
    (initialConversations[0]?.agent_id ?? "") === "octopus_builtin"
      ? "direct_agent"
      : "direct_agent"
  );

  // Kanaloa (builtin) LLM activation
  const [kanaloaLlmActive, setKanaloaLlmActive] = useState<boolean | null>(null);
  const [kanaloaProfile, setKanaloaProfile] = useState<ApiProfile | null>(null);

  // dropdown data for composer bar
  const [skills, setSkills] = useState<SkillLite[]>([]);
  const [credentials, setCredentials] = useState<CredentialLite[]>([]);

  // textarea ref (for slash-command / credential insert)
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const selectedConversation = useMemo(
    () => conversations.find((c) => c.conversation_id === selectedId) ?? null,
    [conversations, selectedId]
  );

  // ---- initial fetches ----
  const checkKanaloaActivation = useCallback(async () => {
    try {
      const resp = await apiGet<{
        api_profile: { binding: { profile_id: string } | null; profile: ApiProfile | null };
      }>("/agents/octopus_builtin");
      const profile = resp.api_profile?.profile ?? null;
      setKanaloaLlmActive(!!profile?.profile_id);
      setKanaloaProfile(profile);
    } catch {
      setKanaloaLlmActive(false);
      setKanaloaProfile(null);
    }
  }, []);

  useEffect(() => {
    checkKanaloaActivation();
  }, [checkKanaloaActivation]);

  useEffect(() => {
    apiGet<ListResponse<SkillLite>>("/skills")
      .then((r) => setSkills(r.items.filter((s) => s.enabled !== false)))
      .catch(() => setSkills([]));
    apiGet<ListResponse<CredentialLite>>("/credentials")
      .then((r) => setCredentials(r.items))
      .catch(() => setCredentials([]));
  }, []);

  // ---- fetch detail when selection changes ----
  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    apiGet<ConversationDetail>(`/conversations/${encodeURIComponent(selectedId)}`)
      .then(setDetail)
      .catch(() => setDetail(null));
  }, [selectedId]);

  useEffect(() => {
    if (!selectedConversation?.agent_id) return;
    setOperatorAgentId(selectedConversation.agent_id);
    setExecutionMode(
      "direct_agent"
    );
    setLastCandidateId(null);
  }, [selectedConversation?.conversation_id, selectedConversation?.agent_id]);

  const isKanaloaOperator = operatorAgentId === "octopus_builtin";
  const operatorAgentName =
    agents.find((a) => a.agent_id === operatorAgentId)?.display_name ?? operatorAgentId;

  // ---------------- actions ----------------

  const createConversation = async () => {
    setBusy(true);
    setErrorText("");
    try {
      const defaultAgent = agents.find((a) => a.agent_id === "octopus_builtin")
        ? "octopus_builtin"
        : agents[0]?.agent_id ?? "octopus_builtin";
      const response = await apiPost<{ data: Conversation }>("/conversations", {
        title: null,
        agent_id: defaultAgent,
      });
      setConversations((prev) => [response.data, ...prev]);
      setSelectedId(response.data.conversation_id);
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  const sendMessage = async () => {
    if (!selectedId || !content.trim()) return;
    setBusy(true);
    setErrorText("");
    setLastCandidateId(null);
    try {
      const response = await apiPost<{
        conversation: Conversation;
        user_message: ConversationMessage;
        assistant_message: ConversationMessage;
        memory_candidate?: { memory_id: string } | null;
      }>(`/conversations/${encodeURIComponent(selectedId)}/messages`, {
        content,
        kind: "chat",
        file_path: null,
        create_memory_candidate: remember,
      });
      setDetail((prev) =>
        prev
          ? {
              ...prev,
              conversation: response.conversation,
              messages: [...prev.messages, response.user_message, response.assistant_message],
            }
          : prev
      );
      setConversations((prev) =>
        prev.map((item) =>
          item.conversation_id === response.conversation.conversation_id
            ? response.conversation
            : item
        )
      );
      setContent("");
      setRemember(false);
      setLastCandidateId(response.memory_candidate?.memory_id ?? null);
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  const switchOperator = async (nextAgentId: string) => {
    if (!selectedId || !nextAgentId) return;
    if (nextAgentId === selectedConversation?.agent_id) {
      setOperatorAgentId(nextAgentId);
      return;
    }
    setBusy(true);
    setErrorText("");
    try {
      const response = await apiPatch<{ data: Conversation }>(
        `/conversations/${encodeURIComponent(selectedId)}`,
        { agent_id: nextAgentId }
      );
      setConversations((prev) =>
        prev.map((item) =>
          item.conversation_id === response.data.conversation_id ? response.data : item
        )
      );
      setDetail((prev) =>
        prev
          ? {
              ...prev,
              conversation: response.data,
              agent: agents.find((a) => a.agent_id === nextAgentId) ?? prev.agent ?? null,
            }
          : prev
      );
      setOperatorAgentId(nextAgentId);
      setExecutionMode("direct_agent");
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : String(error));
      setOperatorAgentId(selectedConversation?.agent_id ?? nextAgentId);
    } finally {
      setBusy(false);
    }
  };

  const renameConversation = async (conv: Conversation) => {
    const next = window.prompt(t("conv.rename_prompt"), conv.title);
    if (next == null) return;
    const title = next.trim();
    if (!title || title === conv.title) return;
    try {
      const response = await apiPatch<{ data: Conversation }>(
        `/conversations/${encodeURIComponent(conv.conversation_id)}`,
        { title }
      );
      setConversations((prev) =>
        prev.map((c) =>
          c.conversation_id === response.data.conversation_id ? response.data : c
        )
      );
      if (detail?.conversation.conversation_id === response.data.conversation_id) {
        setDetail({ ...detail, conversation: response.data });
      }
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : String(error));
    }
  };

  const exportConversation = async (conv: Conversation) => {
    try {
      const payload = await apiGet<ConversationDetail>(
        `/conversations/${encodeURIComponent(conv.conversation_id)}`
      );
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${conv.conversation_id}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : String(error));
    }
  };

  const copyLink = async (conv: Conversation) => {
    try {
      const base =
        typeof window !== "undefined" ? window.location.origin : "";
      await navigator.clipboard?.writeText(
        `${base}/conversations?selected=${encodeURIComponent(conv.conversation_id)}`
      );
    } catch {
      // silent
    }
  };

  const deleteConversation = async (conv: Conversation) => {
    const confirmed = window.confirm(
      t("conv.delete_confirm_body").replace("{title}", conv.title)
    );
    if (!confirmed) return;
    try {
      await apiDelete(`/conversations/${encodeURIComponent(conv.conversation_id)}`);
      setConversations((prev) =>
        prev.filter((c) => c.conversation_id !== conv.conversation_id)
      );
      if (selectedId === conv.conversation_id) {
        setSelectedId(null);
        setDetail(null);
      }
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : String(error));
    }
  };

  const promoteToTask = async () => {
    if (!selectedId) return;
    setBusy(true);
    setErrorText("");
    try {
      const response = await apiPost<{
        conversation: Conversation;
        task: { task_id: string };
      }>(`/conversations/${encodeURIComponent(selectedId)}/promote`, {
        execution_mode: executionMode,
        assign_agent: true,
      });
      setDetail((prev) =>
        prev ? { ...prev, conversation: response.conversation } : prev
      );
      setConversations((prev) =>
        prev.map((item) =>
          item.conversation_id === response.conversation.conversation_id
            ? response.conversation
            : item
        )
      );
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  const insertAtCursor = (snippet: string) => {
    const ta = textareaRef.current;
    if (!ta) {
      setContent((prev) => prev + snippet);
      return;
    }
    const start = ta.selectionStart ?? ta.value.length;
    const end = ta.selectionEnd ?? ta.value.length;
    const before = content.slice(0, start);
    const after = content.slice(end);
    const next = before + snippet + after;
    setContent(next);
    requestAnimationFrame(() => {
      ta.focus();
      const pos = (before + snippet).length;
      ta.setSelectionRange(pos, pos);
    });
  };

  const onComposerKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      void sendMessage();
    }
  };

  const promotedTaskId = detail?.conversation.promoted_task_id ?? null;

  // ---------------- render ----------------

  return (
    <div className="flex h-full min-h-0 w-full">
      {/* LEFT: conversation list */}
      <section className="flex w-72 shrink-0 flex-col border-r border-zinc-200 bg-white">
        <div className="flex items-center justify-between gap-2 border-b border-zinc-200 px-3 py-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
            {t("conv.left.title")}
          </div>
          <button
            data-testid="create-conversation-button"
            type="button"
            disabled={busy}
            onClick={createConversation}
            className="inline-flex h-8 items-center gap-1 rounded-md bg-[var(--octo-royal-blue)] px-2.5 text-xs font-medium text-white disabled:opacity-50"
            title={t("conv.left.new_tooltip")}
          >
            {t("conv.left.new")}
          </button>
        </div>

        {/* preserve this hidden input for E2E compatibility */}
        <input
          data-testid="conversation-title-input"
          className="sr-only"
          tabIndex={-1}
          aria-hidden
          value=""
          onChange={() => undefined}
        />

        <div
          data-testid="conversation-list"
          className="flex-1 overflow-y-auto p-1.5"
        >
          {conversations.length === 0 ? (
            <div className="px-3 py-8 text-center text-xs text-zinc-400">
              {t("conv.left.empty")}
            </div>
          ) : (
            <ul className="space-y-0.5">
              {conversations.map((conv) => {
                const active = selectedId === conv.conversation_id;
                const agent = agents.find((a) => a.agent_id === conv.agent_id);
                return (
                  <li
                    key={conv.conversation_id}
                    data-testid={`conversation-item-${conv.conversation_id}`}
                    className={cx(
                      "group relative flex cursor-pointer items-start gap-2 rounded-md px-2.5 py-2 transition-colors",
                      active ? "bg-[var(--octo-royal-blue)]" : "hover:bg-zinc-50"
                    )}
                    onClick={() => setSelectedId(conv.conversation_id)}
                  >
                    {active && (
                      <span
                        className="absolute left-0 top-2 bottom-2 w-0.5 rounded-r"
                        style={{ background: "#ffffff" }}
                        aria-hidden
                      />
                    )}
                    <div className="min-w-0 flex-1">
                      <div
                        className={cx(
                          "truncate text-sm",
                          active ? "font-semibold text-white" : "text-zinc-800"
                        )}
                      >
                        {conv.title}
                      </div>
                      <div
                        className={cx(
                          "mt-0.5 flex items-center gap-1.5 text-[11px]",
                          active ? "text-blue-100" : "text-zinc-500"
                        )}
                      >
                        <span className="truncate">
                          {agent?.display_name ?? conv.agent_id}
                        </span>
                        <span>·</span>
                        <span>{fmtDate(conv.last_message_at ?? conv.updated_at ?? conv.created_at)}</span>
                        {conv.promoted_task_id ? (
                          <span
                            className={cx(
                              "rounded px-1 py-0.5 text-[10px]",
                              active
                                ? "bg-white/20 text-white"
                                : "bg-zinc-200 text-zinc-700"
                            )}
                            title={t("conv.task_tag_tooltip").replace(
                              "{id}",
                              conv.promoted_task_id
                            )}
                          >
                            {t("conv.task_tag_label")}
                          </span>
                        ) : null}
                      </div>
                    </div>
                    <div className="opacity-0 transition-opacity group-hover:opacity-100">
                      <RowMenu
                        align="right"
                        ariaLabel={t("conv.more_actions")}
                        items={[
                          { label: t("conv.menu.rename"), onClick: () => renameConversation(conv) },
                          {
                            label: t("conv.menu.switch_operator"),
                            onClick: () => {
                              setSelectedId(conv.conversation_id);
                              window.setTimeout(() => {
                                document
                                  .querySelector<HTMLSelectElement>(
                                    "[data-testid='operator-select']"
                                  )
                                  ?.focus();
                              }, 0);
                            },
                          },
                          { label: t("conv.menu.export_json"), onClick: () => exportConversation(conv) },
                          { label: t("conv.menu.copy_link"), onClick: () => copyLink(conv) },
                          { separator: true },
                          {
                            label: t("conv.menu.delete_permanent"),
                            onClick: () => deleteConversation(conv),
                            danger: true,
                          },
                        ]}
                      />
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </section>

      {/* RIGHT: conversation detail */}
      <section className="flex min-w-0 flex-1 flex-col bg-white">
        {!selectedConversation ? (
          <div className="flex flex-1 items-center justify-center text-sm text-zinc-400">
            {t("conv.right.empty_select")}
          </div>
        ) : (
          <>
            {/* top bar of conversation */}
            <header className="flex items-center gap-3 border-b border-zinc-200 px-4 py-2.5">
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-semibold text-zinc-900">
                  {selectedConversation.title}
                </div>
                <div
                  data-testid="selected-conversation-meta"
                  className="mt-0.5 truncate text-[11px] text-zinc-500"
                >
                  {t("conv.meta.operator_prefix")}
                  {operatorAgentName} · {t("conv.meta.status_prefix")}
                  {selectedConversation.status}
                </div>
              </div>

              {/* operator select */}
              <label className="flex items-center gap-1.5 text-[11px] text-zinc-500">
                <span>{t("conv.meta.operator_label")}</span>
                <select
                  data-testid="operator-select"
                  className="rounded-md border border-zinc-200 bg-white px-2 py-1 text-xs"
                  value={operatorAgentId}
                  onChange={(e) => void switchOperator(e.target.value)}
                  disabled={busy}
                >
                  {agents.map((a) => (
                    <option key={a.agent_id} value={a.agent_id}>
                      {a.display_name}
                    </option>
                  ))}
                </select>
              </label>

              {/* right-side ... menu */}
              <RowMenu
                align="right"
                ariaLabel={t("conv.more_actions")}
                items={[
                  {
                    label: t("conv.menu.rename"),
                    onClick: () => renameConversation(selectedConversation),
                  },
                  {
                    label: t("conv.menu.export_json"),
                    onClick: () => exportConversation(selectedConversation),
                  },
                  {
                    label: promotedTaskId
                      ? t("conv.menu.open_task")
                      : t("conv.menu.open_task_disabled"),
                    onClick: () => {
                      if (promotedTaskId) {
                        window.location.href = `/tasks/${encodeURIComponent(promotedTaskId)}`;
                      }
                    },
                    disabled: !promotedTaskId,
                  },
                  { separator: true },
                  {
                    label: t("conv.menu.delete_permanent"),
                    onClick: () => deleteConversation(selectedConversation),
                    danger: true,
                  },
                ]}
              />
            </header>

            {/* mode row — 共享 listModesFor() 保证与操控舱一致 */}
            <div className="border-b border-zinc-200 bg-zinc-50/60 px-4 py-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[11px] text-zinc-500">{t("mode.exec_label")}</span>
                {listModesFor(isKanaloaOperator).map((item) => {
                  const disabled = item.kanaloaOnly && !isKanaloaOperator;
                  const active = executionMode === item.id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      disabled={disabled}
                      onClick={() => setExecutionMode(item.id)}
                      title={disabled ? t("mode.kanaloa_only_hint") : t(item.labelKey)}
                      className={cx(
                        "rounded-full px-2.5 py-0.5 text-[11px] transition-colors",
                        active
                          ? "bg-[var(--octo-royal-blue)] text-white"
                          : disabled
                          ? "cursor-not-allowed bg-zinc-100 text-zinc-400"
                          : "bg-white text-zinc-600 border border-zinc-200 hover:border-[var(--octo-royal-blue)] hover:text-[var(--octo-royal-blue)]"
                      )}
                    >
                      {t(item.labelKey)}
                    </button>
                  );
                })}
                {!isKanaloaOperator && (
                  <span className="text-[10px] text-zinc-400">
                    {t("mode.kanaloa_only_hint")}
                  </span>
                )}
              </div>
            </div>

            {/* candidate inline notice */}
            {lastCandidateId ? (
              <div
                data-testid="memory-candidate-notice"
                className="mx-4 mt-3 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-900"
              >
                Memory candidate created · {lastCandidateId} —
                <Link href="/memory?tab=candidate" className="ml-1 underline">
                  {t("conv.goto_review")}
                </Link>
              </div>
            ) : null}

            {/* messages — bleed into available space */}
            <div
              data-testid="conversation-history"
              className="flex-1 min-h-0 overflow-y-auto px-4 py-4"
            >
              <div className="mx-auto w-full max-w-3xl space-y-3">
                {(() => {
                  type TimelineItem =
                    | { kind: "message"; item: ConversationMessage }
                    | { kind: "task_event"; item: TaskEventVirtualMessage };
                  const timeline: TimelineItem[] = [
                    ...(detail?.messages ?? []).map(
                      (m): TimelineItem => ({ kind: "message" as const, item: m })
                    ),
                    ...(detail?.task_events ?? []).map(
                      (e): TimelineItem => ({ kind: "task_event" as const, item: e })
                    ),
                  ];
                  timeline.sort((a, b) =>
                    a.item.created_at < b.item.created_at ? -1 : 1
                  );
                  return timeline.map((entry) => {
                    if (entry.kind === "task_event") {
                      const e = entry.item;
                      return (
                        <div
                          key={e.message_id}
                          className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-900"
                          data-testid={`conversation-task-event-${e.task_event_type}`}
                        >
                          <div className="text-[10px] opacity-70">
                            {t("conv.system.task_event")} · {e.task_event_type} · {fmtDate(e.created_at)}
                          </div>
                          <div className="mt-1 whitespace-pre-wrap leading-relaxed">
                            {e.content}
                          </div>
                        </div>
                      );
                    }
                    const m = entry.item;
                    return (
                      <div
                        data-testid={`conversation-message-${m.role}-${m.kind}`}
                        key={m.message_id}
                        className={cx(
                          "rounded-lg px-3 py-2 text-sm",
                          m.role === "assistant"
                            ? "border border-zinc-200 bg-white"
                            : m.role === "system"
                            ? "border border-amber-200 bg-amber-50 text-amber-900"
                            : "bg-zinc-900 text-white"
                        )}
                      >
                        <div className="text-[10px] opacity-70">
                          {m.role} · {fmtDate(m.created_at)}
                        </div>
                        <div className="mt-1 whitespace-pre-wrap leading-relaxed">
                          {m.content}
                        </div>
                        {m.references.length ? (
                          <div className="mt-1.5 flex flex-wrap gap-1">
                            {m.references.map((r, i) => (
                              <span
                                key={i}
                                className="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] text-zinc-600"
                                title={JSON.stringify(r)}
                              >
                                {String((r as Record<string, unknown>).type ?? "ref")}
                              </span>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    );
                  });
                })()}
                {(detail?.messages ?? []).length === 0 && (detail?.task_events ?? []).length === 0 && (
                  <div className="py-8 text-center text-xs text-zinc-400">
                    {t("conv.right.empty_timeline")}
                  </div>
                )}
              </div>
            </div>

            {/* capability bar */}
            <div className="border-t border-zinc-200 bg-white px-4 py-3">
              <div className="mx-auto w-full max-w-3xl space-y-2">
                {errorText ? (
                  <div className="rounded-md border border-red-200 bg-red-50 px-2 py-1 text-[11px] text-red-700">
                    {errorText}
                  </div>
                ) : null}

                <textarea
                  data-testid="conversation-message-input"
                  ref={textareaRef}
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  onKeyDown={onComposerKeyDown}
                  placeholder={t("conv.input.placeholder")}
                  className="min-h-[72px] w-full resize-y rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm focus:border-zinc-400 focus:outline-none"
                />

                <div className="flex flex-wrap items-center gap-1.5">
                  {/* model status */}
                  <ModelBadge
                    isKanaloa={isKanaloaOperator}
                    active={kanaloaLlmActive}
                    profile={kanaloaProfile}
                  />

                  {/* skills */}
                  <SkillsDropdown
                    skills={skills}
                    onPick={(s) => insertAtCursor(`/${s.name} `)}
                  />

                  {/* connections */}
                  <CredentialsDropdown
                    credentials={credentials}
                    onPick={(c) =>
                      insertAtCursor(`@${c.provider ?? ""}:${c.name ?? c.credential_id} `)
                    }
                  />

                  {/* remember toggle replaces old checkbox; keep the same test-id for E2E */}
                  <label
                    className={cx(
                      "inline-flex cursor-pointer select-none items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] transition-colors",
                      remember
                        ? "border-amber-300 bg-amber-50 text-amber-800"
                        : "border-zinc-200 bg-white text-zinc-600 hover:border-zinc-400"
                    )}
                    title={t("conv.remember.title")}
                  >
                    <input
                      data-testid="create-memory-candidate-checkbox"
                      type="checkbox"
                      className="sr-only"
                      checked={remember}
                      onChange={(e) => setRemember(e.target.checked)}
                    />
                    <span aria-hidden>📌</span>
                    <span>{t("conv.remember.label")}</span>
                    <span className={cx("text-[10px]", remember ? "text-amber-600" : "text-zinc-400")}>
                      {remember ? t("conv.remember.on") : t("conv.remember.off")}
                    </span>
                  </label>

                  <div className="ml-auto flex items-center gap-1.5">
                    <button
                      data-testid="promote-to-task-button"
                      type="button"
                      disabled={busy}
                      onClick={promoteToTask}
                      className="rounded-md border border-zinc-200 bg-white px-3 py-1.5 text-xs text-zinc-700 hover:border-zinc-400 disabled:opacity-50"
                      title={`${t("action.promote_to_task")} · ${t(
                        modeLabelKey(executionMode, isKanaloaOperator)
                      )}`}
                    >
                      {t("action.promote_to_task")}
                    </button>
                    {promotedTaskId ? (
                      <Link
                        data-testid="open-promoted-task-link"
                        href={`/tasks/${encodeURIComponent(promotedTaskId)}`}
                        className="rounded-md border border-zinc-200 bg-white px-3 py-1.5 text-xs text-zinc-700 hover:border-zinc-400"
                      >
                        {t("action.open_task")}
                      </Link>
                    ) : null}
                    <button
                      data-testid="send-message-button"
                      type="button"
                      disabled={busy || !content.trim()}
                      onClick={sendMessage}
                      className="rounded-md bg-[var(--octo-royal-blue)] px-3 py-1.5 text-xs text-white disabled:opacity-50"
                      title={t("action.send_hint")}
                    >
                      {t("action.send")}
                      <span className="ml-1 text-[10px] opacity-70">⌘⏎</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

// ---------------------- capability-bar sub-components ----------------------

function ModelBadge({
  isKanaloa,
  active,
  profile,
}: {
  isKanaloa: boolean;
  active: boolean | null;
  profile: ApiProfile | null;
}) {
  const t = useT();
  if (!isKanaloa) {
    return (
      <span
        className="inline-flex items-center gap-1 rounded-md border border-zinc-200 bg-zinc-50 px-2 py-1 text-[11px] text-zinc-500"
        title={t("conv.model.external_tooltip")}
      >
        <span aria-hidden>🧠</span>
        <span>{t("conv.model.external_label")}</span>
      </span>
    );
  }
  if (active && profile) {
    return (
      <span
        className="inline-flex items-center gap-1 rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-[11px] text-emerald-800"
        title={t("conv.model.active_tooltip")
          .replace("{name}", profile.name)
          .replace("{model}", profile.model)}
      >
        <span aria-hidden>🧠</span>
        <span>Kanaloa ✓</span>
        <span className="text-[10px] opacity-70">{profile.name}</span>
      </span>
    );
  }
  return (
    <Link
      href="/settings?cat=model"
      className="inline-flex items-center gap-1 rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-800 hover:border-amber-400"
      title={t("conv.model.inactive_tooltip")}
    >
      <span aria-hidden>🧠</span>
      <span>{t("conv.model.inactive_label")}</span>
      <span className="text-[10px] opacity-70">{t("conv.model.go_configure")}</span>
    </Link>
  );
}

function Dropdown({
  label,
  icon,
  disabled,
  items,
  onPick,
  emptyHint,
  itemLabel,
  itemDesc,
}: {
  label: string;
  icon: string;
  disabled?: boolean;
  items: Array<Record<string, unknown>>;
  onPick: (item: Record<string, unknown>) => void;
  emptyHint: string;
  itemLabel: (item: Record<string, unknown>) => string;
  itemDesc?: (item: Record<string, unknown>) => string | null | undefined;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        className={cx(
          "inline-flex items-center gap-1 rounded-md border border-zinc-200 bg-white px-2 py-1 text-[11px] transition-colors",
          disabled
            ? "cursor-not-allowed text-zinc-300"
            : "text-zinc-700 hover:border-zinc-400"
        )}
      >
        <span aria-hidden>{icon}</span>
        <span>{label}</span>
        <span className="text-[10px] opacity-60">▾</span>
      </button>
      {open && (
        <div
          role="menu"
          className="absolute bottom-full left-0 z-20 mb-1 max-h-72 w-60 overflow-y-auto rounded-md border border-zinc-200 bg-white py-1 shadow-lg"
        >
          {items.length === 0 ? (
            <div className="px-3 py-3 text-center text-[11px] text-zinc-400">
              {emptyHint}
            </div>
          ) : (
            items.map((item, idx) => {
              const desc = itemDesc?.(item);
              return (
                <button
                  key={idx}
                  type="button"
                  onClick={() => {
                    setOpen(false);
                    onPick(item);
                  }}
                  className="flex w-full flex-col items-start px-3 py-1.5 text-left text-xs text-zinc-700 hover:bg-zinc-50"
                >
                  <span className="truncate">{itemLabel(item)}</span>
                  {desc ? (
                    <span className="truncate text-[10px] text-zinc-400">{desc}</span>
                  ) : null}
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

function SkillsDropdown({
  skills,
  onPick,
}: {
  skills: SkillLite[];
  onPick: (s: SkillLite) => void;
}) {
  const t = useT();
  return (
    <Dropdown
      label={t("conv.skills.label")}
      icon="🔧"
      items={skills as unknown as Array<Record<string, unknown>>}
      emptyHint={t("conv.skills.empty")}
      itemLabel={(item) => String(item.name ?? item.skill_id)}
      itemDesc={(item) => {
        const scope = item.skill_scope;
        return scope === "agent_private"
          ? t("conv.skills.scope_private")
          : t("conv.skills.scope_platform");
      }}
      onPick={(item) => onPick(item as unknown as SkillLite)}
    />
  );
}

function CredentialsDropdown({
  credentials,
  onPick,
}: {
  credentials: CredentialLite[];
  onPick: (c: CredentialLite) => void;
}) {
  const t = useT();
  return (
    <Dropdown
      label={t("conv.credentials.label")}
      icon="🔗"
      items={credentials as unknown as Array<Record<string, unknown>>}
      emptyHint={t("conv.credentials.empty")}
      itemLabel={(item) =>
        `${(item.provider as string) ?? "credential"} · ${(item.name as string) ?? (item.credential_id as string)}`
      }
      itemDesc={(item) => (item.masked_value as string) ?? null}
      onPick={(item) => onPick(item as unknown as CredentialLite)}
    />
  );
}
