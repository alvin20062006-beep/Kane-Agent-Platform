from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from ..id_utils import new_id
from ..models import (
    Conversation,
    ConversationCreateBody,
    ConversationMessage,
    ConversationMessageBody,
    ConversationPatchBody,
    ConversationPromoteBody,
    ConversationStatus,
    MemoryItem,
    Task,
    TaskAssignBody,
    TaskCreateBody,
    TaskEventRecord,
)
from ..pagination import MEMORY_SEARCH_MAX_HITS, MEMORY_SEARCH_MAX_SCAN
from ..store.repositories import (
    agents_repo,
    conversation_messages_repo,
    conversations_repo,
    memory_repo,
    task_events_repo,
)
from .task_lifecycle import assign_task, create_task
from .llm_client import LLMNotConfiguredError, call_llm
from .kanaloa_actions import try_chat_actions
from .kanaloa_orchestrator import try_orchestrator_chat
from .kanaloa_platform import (
    KANALOA_AGENT_ID,
    build_compact_snapshot_text,
)
from .memory_ledger import record_memory_item_event, user_delete_memory


REPO_ROOT = Path(__file__).resolve().parents[4]


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _append_message(
    conversation_id: str,
    role: str,
    kind: str,
    content: str,
    *,
    agent_id: str | None = None,
    references: list[dict[str, Any]] | None = None,
    create_memory_candidate: bool = False,
) -> ConversationMessage:
    message = ConversationMessage(
        message_id=new_id("msg"),
        conversation_id=conversation_id,
        role=role,  # type: ignore[arg-type]
        kind=kind,  # type: ignore[arg-type]
        content=content,
        agent_id=agent_id,
        created_at=_now_iso(),
        references=references or [],
        create_memory_candidate=create_memory_candidate,
    )
    conversation_messages_repo.upsert(message)
    return message


def _append_task_event(
    task_id: str,
    event_type: str,
    message: str,
    payload: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> None:
    task_events_repo.upsert(
        TaskEventRecord(
            event_id=new_id("evt"),
            task_id=task_id,
            type=event_type,
            message=message,
            payload=payload,
            created_at=_now_iso(),
            correlation_id=correlation_id,
        )
    )


def _update_conversation(conversation: Conversation, **updates: Any) -> Conversation:
    updated = conversation.model_copy(update={"updated_at": _now_iso(), **updates})
    conversations_repo.upsert(updated)
    return updated


def _build_builtin_reply(
    body: ConversationMessageBody,
    conversation: Conversation,
) -> tuple[str, list[dict[str, Any]]]:
    if body.kind == "file_read":
        if not body.file_path:
            raise HTTPException(status_code=400, detail="file_path_required_for_file_read")
        target = (REPO_ROOT / body.file_path).resolve() if not Path(body.file_path).is_absolute() else Path(body.file_path).resolve()
        try:
            target.relative_to(REPO_ROOT)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="file_path_outside_workspace") from exc
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="file_not_found")
        content = target.read_text(encoding="utf-8", errors="replace")
        excerpt = content[:4000]
        return (
            f"Read file `{target}`.\n\nExcerpt:\n{excerpt}",
            [{"type": "file", "path": str(target)}],
        )

    if body.kind == "memory_search":
        query = body.content.lower().strip()
        if not query:
            raise HTTPException(status_code=400, detail="memory_search_query_required")
        items = memory_repo.list()
        items.sort(key=lambda x: x.created_at or "", reverse=True)
        hits = []
        for scanned, item in enumerate(items, start=1):
            if scanned > MEMORY_SEARCH_MAX_SCAN:
                break
            haystack = f"{item.title}\n{item.content}\n{' '.join(item.tags)}".lower()
            if query in haystack:
                hits.append(item)
                if len(hits) >= MEMORY_SEARCH_MAX_HITS:
                    break
        if not hits:
            return (
                "No matching long-term or task memory entries were found for this query.",
                [],
            )
        lines = [
            f"- {item.title} [{item.status}] ({item.scope_type or 'unspecified'}:{item.scope_id or 'n/a'})"
            for item in hits
        ]
        refs = [
            {
                "type": "memory",
                "memory_id": item.memory_id,
                "title": item.title,
                "scope_type": item.scope_type,
                "scope_id": item.scope_id,
            }
            for item in hits
        ]
        return ("Memory search results:\n" + "\n".join(lines), refs)

    if body.kind == "chat" and conversation.agent_id == KANALOA_AGENT_ID:
        orch = try_orchestrator_chat(body.content, conversation.conversation_id)
        if orch:
            return orch, []
        chat_action = try_chat_actions(body.content)
        if chat_action:
            return chat_action, []

    # Build recent conversation context (last 8 turns)
    all_msgs = [
        m for m in conversation_messages_repo.list()
        if m.conversation_id == conversation.conversation_id
        and m.role in ("user", "assistant")
    ]
    all_msgs.sort(key=lambda m: m.created_at)
    recent_turns = all_msgs[-8:]

    # Try real LLM inference first — Kanaloa gets authoritative platform snapshot (no secrets).
    orchestrator_rules = (
        "你是 Kanaloa，Kāne 平台的内置 **Owner 级总控（orchestrator / superuser）**："
        "在用户自有的平台实例里，你应主动调度任务、Adapter 与工具完成工作，不是只读状态面板，也不是默认真只走 dry_run。\n"
        "当用户要求检查/修复/运行测试/提交等时，在「Live platform snapshot」与可用 Agent/Adapter 允许的前提下，应创建并执行（execute）任务，"
        "只有用户明确说 dry_run、不要执行、只做计划、先模拟、只检查不修改时，才用 dry_run。\n"
        "当用户询问平台能力、Agent、Adapter、Bridge、Claude Code、Cursor、MCP、权限、调度或连接状态时，"
        "你必须只依据下方「Live platform snapshot」JSON 作答；禁止编造已连接/未连接。\n"
        "若快照显示 error/missing_config/not_installed/unsupported/not_configured，须如实解释原因。\n"
        "不得声称自己能任意读取用户仓库源代码；你能看到的是快照中的结构化状态。\n"
        "绝不把 API key、token、私钥、.env 原文或凭证明文写入对用户可见的回复（日志同理）；工具可使用环境变量但不要泄露原文。\n"
        "你可以引导用户使用平台的任务系统、Local Bridge 与 Agents 管理能力。\n"
        "若本轮已由服务端执行 Kanaloa Action（列表 Agent、创建 dry_run/execute 任务等），以该 Action 输出为准。\n"
        "回答语言：中文优先，必要时英文。"
    )
    snapshot_block = ""
    if conversation.agent_id == KANALOA_AGENT_ID and body.kind == "chat":
        snapshot_block = (
            "\n\n### Live platform snapshot（权威事实来源）\n"
            + build_compact_snapshot_text()
        )
    system_prompt = orchestrator_rules + snapshot_block
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for m in recent_turns:
        messages.append({"role": m.role, "content": m.content})  # type: ignore[arg-type]
    messages.append({"role": "user", "content": body.content})

    try:
        reply = call_llm(messages)
        return reply, []
    except LLMNotConfiguredError as e:
        # No profile configured — return deterministic reply with prompt
        fallback = (
            f"⚙️ {e}\n\n"
            f"当前会话：{conversation.title}\n"
            "---\n"
            "章鱼 AI 现在以基础确定性模式运行。"
            "配置模型后，我将能够真正理解并回答你的问题。"
        )
        return fallback, []
    except RuntimeError as e:
        return f"章鱼 AI 调用 LLM 时出错：{e}\n\n请检查模型配置或稍后重试。", []


def _maybe_create_memory_candidate(
    conversation: Conversation,
    user_message: ConversationMessage,
    assistant_message: ConversationMessage,
) -> MemoryItem | None:
    if not user_message.create_memory_candidate and not user_message.content.lower().startswith("remember:"):
        return None
    title = user_message.content.splitlines()[0][:120]
    item = MemoryItem(
        memory_id=new_id("mem"),
        memory_type="conversation_candidate",
        title=title or f"Conversation note from {conversation.conversation_id}",
        content=assistant_message.content[:4000],
        confidence=0.55,
        status="candidate",
        source_type="conversation",
        source_id=conversation.conversation_id,
        scope_type="personal",
        scope_id="default",
        tags=["conversation", conversation.agent_id],
        source_agent_id=conversation.agent_id,
        conversation_id=conversation.conversation_id,
        created_at=_now_iso(),
    )
    memory_repo.upsert(item)
    record_memory_item_event(item, event_type="candidate_created", created_by="ai")
    return item


def list_conversations() -> list[Conversation]:
    items = conversations_repo.list()
    items.sort(key=lambda item: item.updated_at or item.created_at, reverse=True)
    return items


def create_conversation(body: ConversationCreateBody) -> Conversation:
    agent = agents_repo.get(body.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="agent_not_found")
    conversation = Conversation(
        conversation_id=new_id("conv"),
        title=(body.title or f"{agent.display_name} conversation").strip(),
        agent_id=body.agent_id,
        status=ConversationStatus.active,
        created_at=_now_iso(),
        updated_at=_now_iso(),
        last_message_at=None,
    )
    conversations_repo.upsert(conversation)
    _append_message(
        conversation.conversation_id,
        "system",
        "system_note",
        f"Conversation created for agent {agent.display_name}.",
        agent_id=body.agent_id,
    )
    return conversation


def get_conversation(conversation_id: str) -> dict[str, Any]:
    conversation = conversations_repo.get(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    messages = [m for m in conversation_messages_repo.list() if m.conversation_id == conversation_id]
    messages.sort(key=lambda item: item.created_at)
    agent = agents_repo.get(conversation.agent_id)

    # C6: merge task events into conversation timeline (as virtual system messages).
    # 这些事件不会真正落库为 conversation_messages，仅在读取时注入，避免冗余。
    task_events_virtual: list[dict[str, Any]] = []
    promoted_task_id = getattr(conversation, "promoted_task_id", None)
    if promoted_task_id:
        raw = [e for e in task_events_repo.list() if e.task_id == promoted_task_id]
        raw.sort(key=lambda e: e.created_at)
        for e in raw:
            task_events_virtual.append(
                {
                    "message_id": f"task_event::{e.event_id}",
                    "conversation_id": conversation_id,
                    "role": "system",
                    "kind": "task_event",
                    "content": e.message or e.type,
                    "file_path": None,
                    "agent_id": None,
                    "created_at": e.created_at,
                    "task_event_type": e.type,
                    "task_id": e.task_id,
                }
            )

    return {
        "conversation": conversation,
        "messages": messages,
        "agent": agent,
        "task_events": task_events_virtual,
        "promoted_task_id": promoted_task_id,
    }


def patch_conversation(conversation_id: str, body: ConversationPatchBody) -> Conversation:
    conversation = conversations_repo.get(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    updates: dict[str, Any] = {}
    if body.title is not None:
        updates["title"] = body.title.strip() or conversation.title
    if body.agent_id is not None:
        agent = agents_repo.get(body.agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="agent_not_found")
        updates["agent_id"] = body.agent_id
        _append_message(
            conversation_id,
            "system",
            "system_note",
            f"Switched operator agent to {agent.display_name}.",
            agent_id=body.agent_id,
        )
    if not updates:
        return conversation
    return _update_conversation(conversation, **updates)


def delete_conversation(conversation_id: str, delete_memory: bool = False) -> dict[str, Any]:
    """
    Physically delete a conversation and its messages.
    - Messages: hard delete (cascading).
    - Memory items: by default only detach `conversation_id` reference; if `delete_memory=True`,
      remove platform memory items that reference this conversation.
    - Tasks promoted from this conversation: keep the tasks, only detach the reference.
    """
    conversation = conversations_repo.get(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    # 1) Cascade messages
    message_ids = [
        m.message_id for m in conversation_messages_repo.list()
        if m.conversation_id == conversation_id
    ]
    for mid in message_ids:
        try:
            conversation_messages_repo.delete(mid)
        except Exception:
            pass

    # 2) Memory items — detach or delete
    memory_touched = 0
    for mem in list(memory_repo.list()):
        if getattr(mem, "conversation_id", None) != conversation_id:
            continue
        if delete_memory:
            try:
                user_delete_memory(mem.memory_id)
                memory_touched += 1
            except Exception:
                pass
        else:
            try:
                updated = mem.model_copy(update={"conversation_id": None})
                memory_repo.upsert(updated)
                record_memory_item_event(
                    updated,
                    event_type="user_rewritten",
                    created_by="user",
                    metadata={"reason": "conversation_deleted_reference_detached"},
                )
                memory_touched += 1
            except Exception:
                pass

    # 3) Delete the conversation itself
    try:
        conversations_repo.delete(conversation_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"delete_failed: {exc}") from exc

    return {
        "conversation_id": conversation_id,
        "deleted_messages": len(message_ids),
        "memory_items_touched": memory_touched,
        "memory_deleted": delete_memory,
    }


def add_conversation_message(conversation_id: str, body: ConversationMessageBody) -> dict[str, Any]:
    conversation = conversations_repo.get(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    agent = agents_repo.get(conversation.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="agent_not_found")

    user_message = _append_message(
        conversation_id,
        "user",
        body.kind,
        body.content.strip(),
        agent_id=conversation.agent_id,
        create_memory_candidate=body.create_memory_candidate,
        references=[{"type": "file", "path": body.file_path}] if body.file_path else [],
    )

    if agent.type == "external":
        reply_text = (
            f"{agent.display_name} is available for formal task execution via Local Bridge. "
            "Lightweight direct chat is intentionally limited; promote this conversation to a task for truthful external handling."
        )
        refs = [{"type": "agent", "agent_id": agent.agent_id, "adapter_id": agent.adapter_id}]
    else:
        reply_text, refs = _build_builtin_reply(body, conversation)

    assistant_message = _append_message(
        conversation_id,
        "assistant",
        body.kind,
        reply_text,
        agent_id=conversation.agent_id,
        references=refs,
    )

    memory_candidate = _maybe_create_memory_candidate(conversation, user_message, assistant_message)
    updated_title = conversation.title
    if conversation.title.endswith("conversation") and body.content:
        updated_title = body.content.splitlines()[0][:80]

    conversation = _update_conversation(
        conversation,
        title=updated_title,
        last_message_at=assistant_message.created_at,
    )
    return {
        "conversation": conversation,
        "user_message": user_message,
        "assistant_message": assistant_message,
        "memory_candidate": memory_candidate,
    }


def promote_conversation_to_task(conversation_id: str, body: ConversationPromoteBody) -> dict[str, Any]:
    detail = get_conversation(conversation_id)
    conversation: Conversation = detail["conversation"]
    agent = detail["agent"]
    messages: list[ConversationMessage] = detail["messages"]
    user_messages = [message for message in messages if message.role == "user"]
    summary_lines = [f"{message.role}: {message.content}" for message in messages[-8:]]
    task_title = body.title or (user_messages[-1].content[:120] if user_messages else conversation.title)
    description = "Promoted from conversation:\n\n" + "\n".join(summary_lines)
    task = create_task(
        TaskCreateBody(
            title=task_title,
            description=description,
            execution_mode=body.execution_mode,
        )
    )
    if body.assign_agent and agent:
        assign_task(task.task_id, TaskAssignBody(agent_id=agent.agent_id))
    _append_task_event(
        task.task_id,
        "promoted_from_conversation",
        f"Promoted from conversation {conversation.conversation_id}",
        {
            "conversation_id": conversation.conversation_id,
            "agent_id": conversation.agent_id,
        },
        correlation_id=task.correlation_id,
    )

    memory = MemoryItem(
        memory_id=new_id("mem"),
        memory_type="task_context",
        title=f"Task context for {task.title}",
        content=description[:4000],
        confidence=0.8,
        status="approved",
        source_type="conversation",
        source_id=conversation.conversation_id,
        scope_type="task",
        scope_id=task.task_id,
        tags=["promoted", conversation.agent_id],
    )
    memory_repo.upsert(memory)
    record_memory_item_event(memory, event_type="observed", created_by="ai")
    _append_message(
        conversation.conversation_id,
        "system",
        "promotion_note",
        f"Promoted to task {task.task_id}.",
        agent_id=conversation.agent_id,
        references=[{"type": "task", "task_id": task.task_id}],
    )
    conversation = _update_conversation(conversation, promoted_task_id=task.task_id)
    return {"conversation": conversation, "task": task}
