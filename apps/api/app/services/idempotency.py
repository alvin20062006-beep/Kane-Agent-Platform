"""HTTP mutation idempotency via processed_action_receipts."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import HTTPException

from .runtime_audit import create_receipt, get_processed_receipt, make_receipt_key


def _fingerprint(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def begin_idempotent_mutation(
    action_type: str,
    idempotency_key: str | None,
    payload: Any,
) -> dict[str, Any] | None:
    """
    When Idempotency-Key is provided, return cached payload on replay or None to proceed.
    Raises 409 when the same key is reused with a different payload fingerprint.
    """
    if not idempotency_key or not idempotency_key.strip():
        return None
    key = idempotency_key.strip()
    fp = _fingerprint(payload)
    receipt_key = make_receipt_key(action_type, key)
    existing = get_processed_receipt("idempotency_api", receipt_key)
    if existing and existing.payload:
        prev_fp = (existing.payload or {}).get("fingerprint")
        cached = (existing.payload or {}).get("response")
        if prev_fp and prev_fp != fp:
            raise HTTPException(status_code=409, detail="idempotency_key_reused_with_different_payload")
        if cached is not None:
            return cached
    return None


def _to_jsonable(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    return obj


def complete_idempotent_mutation(
    action_type: str,
    idempotency_key: str | None,
    payload: Any,
    response: dict[str, Any],
    *,
    task_id: str | None = None,
    run_id: str | None = None,
) -> None:
    if not idempotency_key or not idempotency_key.strip():
        return
    key = idempotency_key.strip()
    receipt_key = make_receipt_key(action_type, key)
    create_receipt(
        "idempotency_api",
        receipt_key,
        task_id=task_id,
        run_id=run_id,
        status="completed",
        payload={"fingerprint": _fingerprint(payload), "response": _to_jsonable(response), "action_type": action_type},
    )
