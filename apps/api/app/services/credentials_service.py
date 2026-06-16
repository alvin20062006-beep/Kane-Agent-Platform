from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from ..id_utils import new_id
from ..models import Credential, CredentialUpsertBody
from ..store.repositories import credentials_repo


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _mask_secret(secret: str | None) -> str | None:
    if not secret:
        return None
    if len(secret) <= 6:
        return "*" * len(secret)
    return f"{secret[:2]}***{secret[-2:]}"


def create_credential(body: CredentialUpsertBody) -> dict:
    now = _now_iso()
    cred_id = new_id("cred")
    ref = body.credential_ref.strip() if body.credential_ref else cred_id
    # Prevent duplicate credential_ref
    for c in credentials_repo.list():
        if c.credential_ref == ref:
            raise HTTPException(status_code=400, detail="credential_ref_exists")

    cred = Credential(
        credential_id=cred_id,
        account_id=body.account_id,
        provider=body.provider,
        credential_type=body.credential_type,
        status="active",
        created_at=now,
        updated_at=now,
        secret_material=body.secret_material,
        credential_ref=ref,
        masked_hint=body.masked_hint or _mask_secret(body.secret_material),
    )
    credentials_repo.upsert(cred)
    # Return masked response
    out = cred.model_copy(update={"secret_material": None})
    return {"data": out, "masked_hint": out.masked_hint}

