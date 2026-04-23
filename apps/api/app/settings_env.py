"""Beta environment (no secrets committed; read from process env)."""

from __future__ import annotations

import os
from pathlib import Path


def get_persistence_backend() -> str:
    # file | postgres
    return os.getenv("OCTOPUS_PERSISTENCE", "file").strip().lower()


def get_database_url() -> str | None:
    # e.g. postgresql+psycopg://user:pass@localhost:5432/octopus
    u = os.getenv("DATABASE_URL") or os.getenv("OCTOPUS_DATABASE_URL")
    return u.strip() if u else None


def get_local_bridge_url() -> str:
    return os.getenv("OCTOPUS_LOCAL_BRIDGE_URL", "http://127.0.0.1:8010").rstrip("/")


def get_bridge_shared_secret() -> str | None:
    return os.getenv("OCTOPUS_BRIDGE_SHARED_SECRET")


def get_openclaw_webhook_url() -> str | None:
    u = os.getenv("OPENCLAW_WEBHOOK_URL")
    return u.strip() if u else None


def get_api_public_url() -> str:
    """Base URL the bridge uses to call back into API (e.g. http://127.0.0.1:8000)."""
    return os.getenv("OCTOPUS_API_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")


def get_api_data_dir() -> Path:
    """Directory for file-backed JSON stores (OCTOPUS_PERSISTENCE=file). Ignored for postgres."""
    raw = os.getenv("OCTOPUS_API_DATA_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data"
