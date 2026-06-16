from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from ..models import BridgeCompleteBody
from ..services.idempotency import begin_idempotent_mutation, complete_idempotent_mutation
from ..services.task_lifecycle import bridge_complete
from ..settings_env import get_bridge_shared_secret
from ..version import PLATFORM_VERSION

router = APIRouter(tags=["integrations"])


@router.post("/integrations/bridge/complete")
def bridge_complete_route(
    body: BridgeCompleteBody,
    x_octopus_bridge_key: str | None = Header(default=None, alias="X-Octopus-Bridge-Key"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """
    Async completion from Local Bridge.
    Optional shared secret: OCTOPUS_BRIDGE_SHARED_SECRET + X-Octopus-Bridge-Key.
    """
    secret = get_bridge_shared_secret()
    if secret and x_octopus_bridge_key != secret:
        raise HTTPException(status_code=401, detail="bridge_auth_failed")
    payload = body.model_dump(mode="json")
    cached = begin_idempotent_mutation("bridge_complete", idempotency_key, payload)
    if cached is not None:
        return cached
    result = bridge_complete(body)
    resp = {"version": PLATFORM_VERSION, **result}
    task_id = body.task_id
    run_id = body.run_id
    complete_idempotent_mutation(
        "bridge_complete",
        idempotency_key,
        payload,
        resp,
        task_id=task_id,
        run_id=run_id,
    )
    return resp
