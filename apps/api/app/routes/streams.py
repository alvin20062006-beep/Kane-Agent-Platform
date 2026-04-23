from __future__ import annotations

import json
import time
from typing import Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..store.repositories import run_logs_repo, task_events_repo, tasks_repo

router = APIRouter(tags=["streams"])


def _sse_pack(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


@router.get("/tasks/{task_id}/events/stream")
def stream_task_events(task_id: str, since: str | None = None):
    task = tasks_repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")

    def gen() -> Iterator[str]:
        last = since
        while True:
            events = [e for e in task_events_repo.list() if e.task_id == task_id]
            events.sort(key=lambda x: x.created_at)
            for e in events:
                if last and e.created_at <= last:
                    continue
                last = e.created_at
                yield _sse_pack("task_event", e.model_dump())
            time.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/runs/{run_id}/logs/stream")
def stream_run_logs(run_id: str, since_seq: int = 0):
    def gen() -> Iterator[str]:
        last_seq = since_seq
        while True:
            logs = [l for l in run_logs_repo.list() if l.run_id == run_id and l.seq > last_seq]
            logs.sort(key=lambda x: x.seq)
            for l in logs:
                last_seq = max(last_seq, l.seq)
                yield _sse_pack("run_log", l.model_dump())
            time.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream")

