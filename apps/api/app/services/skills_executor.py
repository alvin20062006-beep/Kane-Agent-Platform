from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException

from ..security.url_safety import is_safe_http_url

from ..id_utils import new_id
from ..models import SkillExecuteBody, SkillExecuteResult
from .policy_engine import explain_skill_execution
from .advisor import upsert_advisor_suggestion
from .skills.connect_agent_skill import execute_connect_agent_skill
from .skills.handoff_guide_skill import execute_handoff_guide_skill
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
    # credential_ref maps to credential_id by default
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
    policy = explain_skill_execution(skill)
    policy_meta = {
        "effective_mode": policy.effective_mode,
        "policy_source": policy.policy_source,
        "matched_policy_id": policy.matched_policy_id,
        "matched_policy_scope": policy.matched_policy_scope,
        "reason": policy.reason,
    }

    # Optional audit hooks
    if body.task_id:
        _append_event(body.task_id, "skill_selected", f"Skill selected: {skill_id}", {"skill_id": skill_id})
    if body.run_id:
        _append_run_log(body.run_id, 100, "info", f"skill_selected {skill_id}", {"skill_id": skill_id})

    if body.task_id:
        _append_event(
            body.task_id,
            "skill_policy_evaluated",
            f"Skill policy evaluated: {policy.effective_mode}",
            {"skill_id": skill_id, **policy_meta},
        )
    if body.run_id:
        _append_run_log(body.run_id, 100, "info", f"skill_policy_evaluated {skill_id}", policy_meta)

    if policy.effective_mode == "confirm":
        if body.task_id:
            _append_event(
                body.task_id,
                "skill_blocked",
                f"Skill blocked by confirm policy: {skill_id}",
                {"skill_id": skill_id, **policy_meta},
            )
        if body.run_id:
            _append_run_log(body.run_id, 101, "warn", f"skill_blocked {skill_id}", policy_meta)
        blocked_count = sum(
            1
            for event in task_events_repo.list()
            if event.type == "skill_blocked" and (event.payload or {}).get("skill_id") == skill_id
        )
        if not body.task_id:
            blocked_count += 1
        if blocked_count >= 2:
            evidence_refs: list[dict[str, Any]] = [{"kind": "skill", "id": skill.skill_id}]
            if body.task_id:
                evidence_refs.append({"kind": "task", "id": body.task_id})
            if body.run_id:
                evidence_refs.append({"kind": "run", "id": body.run_id})
            upsert_advisor_suggestion(
                suggestion_type="policy_draft_suggestion",
                target_type="skill",
                target_id=skill.skill_id,
                pattern_key=f"skill_confirm_gate:{skill.skill_id}",
                title="Review skill default execution policy",
                summary="This skill is frequently blocked by a confirm gate.",
                rationale=(
                    f"Skill {skill.skill_id} has been blocked by confirm mode at least {blocked_count} times "
                    f"with effective policy source {policy.policy_source}."
                ),
                recommended_action="Review the skill default_execution_policy and the matched policy before using auto or notify.",
                evidence_refs=evidence_refs,
                severity="warning",
                requires_confirmation=True,
                correlation_id=None,
                source_task_id=body.task_id,
                source_run_id=body.run_id,
            )
        return SkillExecuteResult(
            ok=False,
            error="skill_policy_confirm_required",
            meta={"kind": "policy_gate", **policy_meta},
        )

    if body.task_id:
        _append_event(body.task_id, "skill_called", f"Skill called: {skill_id}", {"skill_id": skill_id})
    if body.run_id:
        _append_run_log(body.run_id, 102, "info", f"skill_called {skill_id}", {"input_keys": sorted(list(input_payload.keys()))})

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
            _append_run_log(body.run_id, 103, "info", f"skill_succeeded {skill_id}", {"output_keys": list(result.keys())})
        return SkillExecuteResult(
            ok=True,
            output=result,
            meta={
                "kind": "builtin",
                **policy_meta,
                **({"policy_notice": "Execution continued under notify policy."} if policy.effective_mode == "notify" else {}),
            },
        )

    # 2) http_request (real outbound HTTP)
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
        if not is_safe_http_url(url):
            return SkillExecuteResult(ok=False, error="url_not_allowed", meta={"url": url})
        if method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"):
            return SkillExecuteResult(ok=False, error="method_not_allowed", meta={"method": method})

        try:
            with httpx.Client(timeout=timeout_s) as client:
                r = client.request(method, url, headers=headers, content=(body_text.encode("utf-8") if isinstance(body_text, str) else None))
                text = r.text
                safe_headers = {k: v for k, v in dict(r.headers).items() if k.lower() not in ("authorization", "set-cookie")}
                out = {
                    "status_code": r.status_code,
                    "headers": safe_headers,
                    "text_excerpt": text[:4000],
                }
                if body.task_id:
                    _append_event(body.task_id, "skill_succeeded" if r.status_code < 400 else "skill_failed", f"HTTP {method} {url} -> {r.status_code}", {"skill_id": skill_id, "status_code": r.status_code})
                if body.run_id:
                    _append_run_log(body.run_id, 103, "info" if r.status_code < 400 else "error", f"http_request status={r.status_code}", {"url": url})
                return SkillExecuteResult(
                    ok=r.status_code < 400,
                    output=out,
                    error=None if r.status_code < 400 else f"http_{r.status_code}",
                    meta={
                        "kind": "http",
                        **policy_meta,
                        **({"policy_notice": "Execution continued under notify policy."} if policy.effective_mode == "notify" else {}),
                    },
                )
        except Exception as e:  # noqa: BLE001
            if body.task_id:
                _append_event(body.task_id, "skill_failed", f"HTTP request failed: {e}", {"skill_id": skill_id})
            if body.run_id:
                _append_run_log(body.run_id, 103, "error", f"http_request_failed: {e}", {"url": url})
            return SkillExecuteResult(ok=False, error=str(e), meta={"kind": "http", **policy_meta})

    # 3) connect_agent (platform onboarding)
    if skill_id == "skill_connect_agent":
        result = execute_connect_agent_skill(input_payload, body)
        if body.task_id:
            _append_event(
                body.task_id,
                "skill_succeeded" if result.ok else "skill_failed",
                f"Connect agent step: {input_payload.get('step', 'guide')}",
                {"skill_id": skill_id, "step": input_payload.get("step"), "error": result.error},
            )
        if body.run_id:
            _append_run_log(
                body.run_id,
                103,
                "info" if result.ok else "error",
                f"skill_connect_agent {input_payload.get('step')}",
                {"ok": result.ok},
            )
        return SkillExecuteResult(
            ok=result.ok,
            output=result.output,
            error=result.error,
            meta={
                **(result.meta or {}),
                **policy_meta,
                **({"policy_notice": "Execution continued under notify policy."} if policy.effective_mode == "notify" else {}),
            },
        )

    if skill_id == "skill_handoff_guide":
        result = execute_handoff_guide_skill(input_payload, body)
        if body.task_id:
            _append_event(
                body.task_id,
                "skill_succeeded" if result.ok else "skill_failed",
                "Handoff guide generated",
                {"skill_id": skill_id, "error": result.error},
            )
        return SkillExecuteResult(
            ok=result.ok,
            output=result.output,
            error=result.error,
            meta={**(result.meta or {}), **policy_meta},
        )

    # default: unsupported
    if body.task_id:
        _append_event(body.task_id, "skill_failed", f"Skill not executable: {skill_id}", {"skill_id": skill_id})
    if body.run_id:
        _append_run_log(body.run_id, 103, "error", f"skill_not_executable {skill_id}", None)
    return SkillExecuteResult(
        ok=False,
        error="skill_not_executable",
        meta={"skill_id": skill_id, "note": skill.description, **policy_meta},
    )

