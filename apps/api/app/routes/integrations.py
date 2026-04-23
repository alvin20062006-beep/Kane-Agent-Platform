from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from ..models import BridgeCompleteBody
from ..services.task_lifecycle import bridge_complete
from ..settings_env import get_bridge_shared_secret

router = APIRouter(tags=["integrations"])


@router.post("/integrations/bridge/complete")
def bridge_complete_route(
    body: BridgeCompleteBody,
    x_octopus_bridge_key: str | None = Header(default=None, alias="X-Octopus-Bridge-Key"),
):
    """
    Async completion from Local Bridge.
    Beta: optional shared secret via OCTOPUS_BRIDGE_SHARED_SECRET + X-Octopus-Bridge-Key.
    """
    secret = get_bridge_shared_secret()
    if secret and x_octopus_bridge_key != secret:
        raise HTTPException(status_code=401, detail="bridge_auth_failed")
    return bridge_complete(body)
