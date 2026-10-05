"""Turn Query, Controls (Cancel / Resume / Stop-Loop), Permissions, and SSE Streaming."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..domain.models import Turn
from ..harness.coordinator import HarnessCoordinator
from ..harness.dispatcher import Dispatcher
from ..store.base import BaseStore
from .deps import get_coordinator, get_dispatcher, get_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["turns"])


# --- Request DTOs ---

PermissionDecision = Literal["allow-once", "reject-once", "cancelled"]


class RespondPermissionRequest(BaseModel):
    decision: PermissionDecision


class PendingPermissionView(BaseModel):
    request_id: str
    title: str
    created_at: float


class LoopView(BaseModel):
    current_iteration: int
    max_iterations: int | None
    stop_requested: bool


class ActivityView(BaseModel):
    event_id: str
    event_type: str
    created_at: str
    payload: dict[str, str]


class TurnDetailResponse(Turn):
    pending_permissions: list[PendingPermissionView] = Field(default_factory=list)
    loop: LoopView | None = None
    events: list[ActivityView] = Field(default_factory=list)


# --- Endpoints ---

@router.get("/turns/{turn_id}", response_model=TurnDetailResponse)
async def get_turn(
    turn_id: str,
    store: BaseStore = Depends(get_store),
    coordinator: HarnessCoordinator = Depends(get_coordinator),
) -> TurnDetailResponse:
    """Retrieve runtime facts and state for a Turn (§8)."""
    turn = store.get_turn(turn_id)
    if not turn:
        raise HTTPException(status_code=404, detail=f"Turn '{turn_id}' not found")
    detail = TurnDetailResponse(**turn.model_dump())
    if coordinator.has_adapter(turn.bound_agent_id):
        adapter = coordinator.get_adapter(turn.bound_agent_id)
        if hasattr(adapter, "list_pending_permissions"):
            for permission in adapter.list_pending_permissions(session_id=turn.native_session_ref):
                if permission.turn_id != turn_id:
                    continue
                tool_call = getattr(permission, "tool_call", {}) or {}
                detail.pending_permissions.append(PendingPermissionView(
                    request_id=str(permission.request_id),
                    title=str(getattr(permission, "title", None) or tool_call.get("title") or tool_call.get("toolName") or tool_call.get("name") or "Agent permission request"),
                    created_at=permission.created_at,
                ))
        runtime = getattr(adapter, "runtime", None)
        if runtime and runtime.is_loop_active(turn_id):
            # Read the existing runtime fact; this DTO owns no execution state.
            loop = runtime._active_loops[turn_id]
            detail.loop = LoopView(
                current_iteration=loop["current_iteration"],
                max_iterations=loop["max_iterations"],
                stop_requested=bool(loop.get("stopped")),
            )
    for event in store.list_events(turn_id):
        if event.event_type in ("raw", "delta"):
            continue
        # Never expose thought text or arbitrary tool arguments in the inspector.
        keys = ("status",) if event.event_type == "thinking" else ("status", "tool", "boundary")
        detail.events.append(ActivityView(
            event_id=event.event_id,
            event_type=event.event_type,
            created_at=event.created_at,
            payload={key: event.payload[key] for key in keys if isinstance(event.payload.get(key), str)},
        ))
    detail.events = detail.events[-40:]
    return detail


@router.post("/turns/{turn_id}/cancel", response_model=Turn)
async def cancel_turn(
    turn_id: str,
    dispatcher: Dispatcher = Depends(get_dispatcher),
) -> Turn:
    """Cancel an active Turn using native cancellation (§11)."""
    try:
        return await dispatcher.cancel_turn(turn_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/turns/{turn_id}/resume", response_model=Turn)
async def resume_turn(
    turn_id: str,
    dispatcher: Dispatcher = Depends(get_dispatcher),
) -> Turn:
    """Resume an interrupted or paused Turn natively (§11)."""
    try:
        return await dispatcher.resume_turn(turn_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/turns/{turn_id}/stop-loop", response_model=Turn)
async def stop_loop(
    turn_id: str,
    dispatcher: Dispatcher = Depends(get_dispatcher),
) -> Turn:
    """Request graceful stop for an active loop Turn (§11)."""
    try:
        return dispatcher.stop_loop(turn_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/turns/{turn_id}/permissions/{request_id}/respond")
async def respond_permission(
    turn_id: str,
    request_id: str,
    body: RespondPermissionRequest,
    store: BaseStore = Depends(get_store),
    coordinator: HarnessCoordinator = Depends(get_coordinator),
) -> dict[str, str]:
    """
    Respond to an in-flight permission request for a Turn (§12).
    Session validation and fail-closed checks are enforced by the underlying adapter.
    """
    turn = store.get_turn(turn_id)
    if not turn:
        raise HTTPException(status_code=404, detail=f"Turn '{turn_id}' not found")

    if not coordinator.has_adapter(turn.bound_agent_id):
        raise HTTPException(
            status_code=503,
            detail=f"No adapter registered for agent '{turn.bound_agent_id}'",
        )

    adapter = coordinator.get_adapter(turn.bound_agent_id)
    if not adapter.capabilities().supports_approval:
        raise HTTPException(
            status_code=400,
            detail=f"Agent '{turn.bound_agent_id}' does not support permissions",
        )

    if hasattr(adapter, "list_pending_permissions") and not any(
        str(permission.request_id) == request_id and permission.turn_id == turn_id
        for permission in adapter.list_pending_permissions(session_id=turn.native_session_ref)
    ):
        raise HTTPException(status_code=400, detail="Permission does not belong to this Turn")

    try:
        await adapter.respond_permission(
            request_id=request_id,
            decision=body.decision,
            session_id=turn.native_session_ref,
        )
        return {
            "turn_id": turn_id,
            "request_id": request_id,
            "decision": body.decision,
            "status": "resolved",
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except NotImplementedError:
        raise HTTPException(status_code=400, detail="Agent does not support permissions")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/turns/{turn_id}/stream")
async def stream_turn_events(
    turn_id: str,
    request: Request,
    store: BaseStore = Depends(get_store),
    coordinator: HarnessCoordinator = Depends(get_coordinator),
) -> StreamingResponse:
    """
    Project live Turn events as Server-Sent Events (SSE) (§14, §15, §16, §17).
    - Subscribes to HarnessCoordinator event bus.
    - Yields initial state snapshot.
    - Disconnect safely cleans up subscription WITHOUT cancelling the Turn.
    """
    turn = store.get_turn(turn_id)
    if not turn:
        raise HTTPException(status_code=404, detail=f"Turn '{turn_id}' not found")

    async def sse_event_stream():
        queue = coordinator.subscribe(turn_id)
        try:
            current_turn = store.get_turn(turn_id)
            if not current_turn:
                return
            # 1. Send initial state snapshot
            snapshot_payload = {
                "turn_id": current_turn.turn_id,
                "status": current_turn.status,
                "partial_output": current_turn.partial_output,
            }
            yield f"event: snapshot\ndata: {json.dumps(snapshot_payload, ensure_ascii=False)}\n\n"

            # If already finished, failed, or interrupted, stream is done after snapshot
            if current_turn.status in ("finished", "failed", "interrupted"):
                return

            # 2. Stream live events
            while True:
                if await request.is_disconnected():
                    logger.debug("SSE client disconnected for turn %s", turn_id)
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    data_str = json.dumps(event.model_dump(), ensure_ascii=False)
                    yield f"event: {event.event_type}\ndata: {data_str}\n\n"

                    # If turn reached terminal status in this event, terminate stream cleanly
                    if event.event_type == "status_change":
                        st = event.payload.get("status")
                        if st in ("finished", "failed", "interrupted"):
                            break
                except asyncio.TimeoutError:
                    if await request.is_disconnected():
                        break
                    yield ": keepalive\n\n"
        finally:
            coordinator.unsubscribe(turn_id, queue)
            logger.debug("SSE subscription cleaned up for turn %s", turn_id)

    return StreamingResponse(
        sse_event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
