from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import text

from .db import ensure_schema, get_db

T = TypeVar("T", bound=BaseModel)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class DbStore(Generic[T]):
    """
    Postgres-backed store using a single entity table (entity_type + entity_id + JSONB payload).
    This preserves the existing repository API (list/get/upsert) while enabling:
    - durable DB persistence
    - concurrent safe upserts
    - Alembic-managed schema (octopus_entities)
    """

    def __init__(self, entity_type: str, model: type[T], id_field: str):
        self.entity_type = entity_type
        self.model = model
        self.id_field = id_field
        ensure_schema()

    def list(self) -> list[T]:
        db = get_db()
        q = text("SELECT data FROM octopus_entities WHERE entity_type=:t ORDER BY updated_at DESC")
        with db.engine.begin() as conn:
            rows = conn.execute(q, {"t": self.entity_type}).fetchall()
        out: list[T] = []
        for (data,) in rows:
            # data may already be dict (psycopg) or string
            if isinstance(data, str):
                payload = json.loads(data)
            else:
                payload = data
            out.append(self.model.model_validate(payload))
        return out

    def get(self, item_id: str) -> T | None:
        db = get_db()
        q = text("SELECT data FROM octopus_entities WHERE entity_type=:t AND entity_id=:id")
        with db.engine.begin() as conn:
            row = conn.execute(q, {"t": self.entity_type, "id": item_id}).fetchone()
        if not row:
            return None
        (data,) = row
        payload = json.loads(data) if isinstance(data, str) else data
        return self.model.model_validate(payload)

    def upsert(self, item: T) -> T:
        db = get_db()
        item_id = str(getattr(item, self.id_field))
        payload = item.model_dump()
        now = _now_iso()
        q = text(
            """
            INSERT INTO octopus_entities(entity_type, entity_id, data, created_at, updated_at)
            VALUES (:t, :id, CAST(:data AS jsonb), now(), now())
            ON CONFLICT(entity_type, entity_id)
            DO UPDATE SET data=EXCLUDED.data, updated_at=now();
            """
        )
        with db.engine.begin() as conn:
            conn.execute(q, {"t": self.entity_type, "id": item_id, "data": json.dumps(payload, ensure_ascii=False)})
        return item

    def delete(self, item_id: str) -> bool:
        """Remove an entity by id. Returns True if a row was deleted."""
        db = get_db()
        q = text("DELETE FROM octopus_entities WHERE entity_type=:t AND entity_id=:id")
        with db.engine.begin() as conn:
            result = conn.execute(q, {"t": self.entity_type, "id": item_id})
        return result.rowcount > 0

