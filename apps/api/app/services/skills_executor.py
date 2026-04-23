from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException

from ..id_utils import new_id
from ..models import SkillExecuteBody, SkillExecuteResult
from ..skill_visibility import skill_is_user_visible
from ..store.repositories import credentials_repo, run_logs_repo, skills_repo, task_events_repo


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _append_event(task_id: str, typ: str, message: str | None, payload: dict[str, Any] | None = None) -> None:
    task_events_repo.upsert(
        task_events_repo.model.model_validate(
            {
                "event_id": new_id("evt"),
                "task_id": task_id,
                "type": typ,
                "message": message,
                "payload": payload,
                "created_at": _now_iso(),
            }
        )
    )


def _append_run_log(run_id: str, seq: int, level: str, message: str, meta: dict[str, Any] | None = None) -> None:
    run_logs_repo.upsert(
        run_logs_repo.model.model_validate(
            {
                "log_id": new_id("log"),
                "run_id": run_id,
                "seq": seq,
                "level": level,
                "message": message,
                "meta": meta,
                "created_at": _now_iso(),
            }
        )
    )


def _get_credential_secret(ref: str) -> str | None:
    # Beta: credential_ref maps to credential_id by default
    items = credentials_repo.list()
    for c in items:
        if c.credential_ref == ref or c.credential_id == ref:
            return c.secret_material
    return None


def execute_skill(skill_id: str, body: SkillExecuteBody) -> SkillExecuteResult:
    skill = skills_repo.get(skill_id)
    if not skill or not skill_is_user_visible(skill):
        raise HTTPException(status_code=404, detail="skill_not_found")

    input_payload = body.input or {}

    # Optional audit hooks
    if body.task_id:
        _append_event(body.task_id, "skill_selected", f"Skill selected: {skill_id}", {"skill_id": skill_id})
    if body.run_id:
        _append_run_log(body.run_id, 100, "info", f"skill_selected {skill_id}", {"skill_id": skill_id})

    if body.task_id:
        _append_event(body.task_id, "skill_called", f"Skill called: {skill_id}", {"skill_id": skill_id})
    if body.run_id:
        _append_run_log(body.run_id, 101, "info", f"skill_called {skill_id}", {"input_keys": sorted(list(input_payload.keys()))})

    # 1) text_summarize (pure builtin)
    if skill_id == "skill_text_summarize":
        text = str(input_payload.get("text", ""))
        max_len = int(input_payload.get("max_len", 240))
        out = text.strip().replace("\r\n", "\n")
        if len(out) > max_len:
            out = out[: max_len - 1].rstrip() + "…"
        result = {"summary": out, "max_len": max_len}
        if body.task_id:
            _append_event(body.task_id, "skill_succeeded", f"Skill succeeded: {skill_id}", {"skill_id": skill_id})
        if body.run_id:
            _append_run_log(body.run_id, 102, "info", f"skill_succeeded {skill_id}", {"output_keys": list(result.keys())})
        return SkillExecuteResult(ok=True, output=result, meta={"kind": "builtin"})

    # 2) http_request (real outbound HTTP; beta)
    if skill_id == "skill_http_request":
        url = str(input_payload.get("url", "")).strip()
        method = str(input_payload.get("method", "GET")).upper()
        headers = input_payload.get("headers") or {}
        if not isinstance(headers, dict):
            raise HTTPException(status_code=400, detail="headers_must_be_object")
        body_text = input_payload.get("body")
        timeout_s = float(input_payload.get("timeout_s", 15))

        # Optional auth via credential_ref
        cred_ref = input_payload.get("credential_ref")
        if isinstance(cred_ref, str) and cred_ref.strip():
            secret = _get_credential_secret(cred_ref.strip())
            if secret:
                headers = {**headers, "Authorization": f"Bearer {secret}"}
            else:
                return SkillExecuteResult(ok=False, error="credential_ref_not_found", meta={"credential_ref": cred_ref})

        if not url.startswith("http"):
            return SkillExecuteResult(ok=False, error="invalid_url", meta={"url": url})

        try:
            with httpx.Client(timeout=timeout_s) as client:
                r = client.request(method, url, headers=headers, content=(body_text.encode("utf-8") if isinstance(body_text, str) else None))
                text = r.text
                out = {
                    "status_code": r.status_code,
                    "headers": dict(r.headers),
                    "text_excerpt": text[:4000],
                }
                if body.task_id:
                    _append_event(body.task_id, "skill_succeeded" if r.status_code < 400 else "skill_failed", f"HTTP {method} {url} -> {r.status_code}", {"skill_id": skill_id, "status_code": r.status_code})
                if body.run_id:
                    _append_run_log(body.run_id, 102, "info" if r.status_code < 400 else "error", f"http_request status={r.status_code}", {"url": url})
                return SkillExecuteResult(ok=r.status_code < 400, output=out, error=None if r.status_code < 400 else f"http_{r.status_code}", meta={"kind": "http"})
        except Exception as e:  # noqa: BLE001
            if body.task_id:
                _append_event(body.task_id, "skill_failed", f"HTTP request failed: {e}", {"skill_id": skill_id})
            if body.run_id:
                _append_run_log(body.run_id, 102, "error", f"http_request_failed: {e}", {"url": url})
            return SkillExecuteResult(ok=False, error=str(e), meta={"kind": "http"})

    # default: unsupported
    if body.task_id:
        _append_event(body.task_id, "skill_failed", f"Skill not executable: {skill_id}", {"skill_id": skill_id})
    if body.run_id:
        _append_run_log(body.run_id, 102, "error", f"skill_not_executable {skill_id}", None)
    return SkillExecuteResult(ok=False, error="skill_not_executable", meta={"skill_id": skill_id, "note": skill.description})

