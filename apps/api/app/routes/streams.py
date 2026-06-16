from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..store.repositories import runs_repo, tasks_repo
from ..store.run_log_queries import list_logs_for_run_since
from ..store.task_event_queries import list_events_for_task

router = APIRouter(tags=["streams"])

_TERMINAL_TASK = frozenset({"succeeded", "failed", "cancelled", "expired"})
_TERMINAL_RUN = frozenset({"succeeded", "failed"})


def _sse_pack(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


@router.get("/tasks/{task_id}/events/stream")
async def stream_task_events(task_id: str, request: Request, since: str | None = None) -> StreamingResponse:
    task = tasks_repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")

    async def gen() -> AsyncIterator[str]:
        last = since
        try:
            while True:
                if await request.is_disconnected():
                    break
                events, _total = list_events_for_task(task_id)
                sent_this_tick = False
                for event in events:
                    if last and event.created_at <= last:
                        continue
                    last = event.created_at
                    sent_this_tick = True
                    yield _sse_pack("task_event", event.model_dump())
                current = tasks_repo.get(task_id)
                if current and current.status.value in _TERMINAL_TASK and not sent_this_tick:
                    break
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            return

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/runs/{run_id}/logs/stream")
async def stream_run_logs(run_id: str, request: Request, since_seq: int = 0) -> StreamingResponse:
    run = runs_repo.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")

    async def gen() -> AsyncIterator[str]:
        last_seq = since_seq
        try:
            while True:
                if await request.is_disconnected():
                    break
                logs = list_logs_for_run_since(run_id, last_seq)
                sent_this_tick = False
                for line in logs:
                    last_seq = max(last_seq, line.seq)
                    sent_this_tick = True
                    yield _sse_pack("run_log", line.model_dump())
                current = runs_repo.get(run_id)
                if current and current.status in _TERMINAL_RUN and not sent_this_tick:
                    break
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            return

    return StreamingResponse(gen(), media_type="text/event-stream")
