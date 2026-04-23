from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, create_engine, text

from ..settings_env import get_database_url


@dataclass(frozen=True)
class Db:
    engine: Engine


_DB: Db | None = None


def get_db() -> Db:
    global _DB
    if _DB:
        return _DB
    url = get_database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is required when OCTOPUS_PERSISTENCE=postgres")
    engine = create_engine(url, pool_pre_ping=True, future=True)
    _DB = Db(engine=engine)
    return _DB


def ensure_schema() -> None:
    """
    Minimal bootstrap for DB mode:
    - relies on Alembic for real migrations
    - but ensures the base table exists if migrations weren't run (beta operator safety)
    """
    db = get_db()
    ddl = """
    CREATE TABLE IF NOT EXISTS octopus_entities (
      entity_type TEXT NOT NULL,
      entity_id TEXT NOT NULL,
      data JSONB NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      PRIMARY KEY (entity_type, entity_id)
    );
    """
    with db.engine.begin() as conn:
        conn.execute(text(ddl))
