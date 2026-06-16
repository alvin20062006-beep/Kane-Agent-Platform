"""Environment configuration (no secrets committed; read from process env)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal


KanePermissionProfile = Literal["owner", "safe", "readonly"]


def get_kane_permission_profile() -> KanePermissionProfile:
    """
    Kanaloa permission profile for self-hosted vs shared deployments.

    - owner: full orchestration (default for this product; private/local).
    - safe: stricter execute gates (e.g. requires OCTOPUS_KANALOA_ADAPTER_EXECUTE for external runs).
    - readonly: list/status only; no task mutation.

    Unset → owner. Production operators may set KANE_PERMISSION_PROFILE=safe for shared instances
    (see README).
    """
    raw = (os.getenv("KANE_PERMISSION_PROFILE") or "").strip().lower()
    if not raw or raw == "default":
        return "owner"
    if raw in ("owner", "superuser", "super"):
        return "owner"
    if raw in ("safe", "restricted"):
        return "safe"
    if raw in ("readonly", "read_only", "read-only", "ro"):
        return "readonly"
    return "owner"


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


def get_api_token() -> str | None:
    """When set, mutating API routes require X-Api-Key or Authorization: Bearer."""
    raw = os.getenv("OCTOPUS_API_TOKEN") or os.getenv("OCTOPUS_API_KEY")
    return raw.strip() if raw and raw.strip() else None


def get_cors_allow_origins() -> list[str]:
    raw = (os.getenv("OCTOPUS_CORS_ORIGINS") or "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ]


def get_bridge_workspace_root() -> Path | None:
    """Optional cwd jail for local_script on Bridge (absolute path)."""
    raw = (os.getenv("OCTOPUS_BRIDGE_WORKSPACE_ROOT") or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def get_openclaw_webhook_url() -> str | None:
    u = os.getenv("OPENCLAW_WEBHOOK_URL")
    return u.strip() if u else None


def get_llm_max_tokens() -> int | None:
    """
    Optional cap for chat/completions. None = omit max_tokens (provider default).

    Reads OCTOPUS_LLM_MAX_TOKENS first, then LLM_MAX_TOKENS.
    Values: unlimited, infinite, auto, none, 0, -1 (all mean no cap / omit param).
    Positive integer = send as max_tokens (and fallbacks in llm_client may use it).
    Invalid or empty → None (no cap from platform).
    """
    raw = (os.getenv("OCTOPUS_LLM_MAX_TOKENS") or os.getenv("LLM_MAX_TOKENS") or "").strip()
    if not raw:
        return None
    low = raw.lower()
    if low in ("unlimited", "infinite", "auto", "none", "-1", "0"):
        return None
    try:
        n = int(raw, 10)
        if n <= 0:
            return None
        return n
    except ValueError:
        return None


def get_api_public_url() -> str:
    """Base URL the bridge uses to call back into API (e.g. http://127.0.0.1:8000)."""
    return os.getenv("OCTOPUS_API_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")


def get_api_data_dir() -> Path:
    """Directory for file-backed JSON stores (OCTOPUS_PERSISTENCE=file). Ignored for postgres."""
    raw = os.getenv("OCTOPUS_API_DATA_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data"


def get_runtime_supervision_enabled() -> bool:
    raw = os.getenv("OCTOPUS_RUNTIME_SUPERVISION_ENABLED", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def get_stalled_task_minutes() -> int:
    raw = os.getenv("OCTOPUS_STALLED_TASK_MINUTES", "15").strip()
    try:
        return max(1, min(int(raw), 1440))
    except ValueError:
        return 15


def get_callback_wait_minutes() -> int:
    raw = os.getenv("OCTOPUS_CALLBACK_WAIT_MINUTES", "10").strip()
    try:
        return max(1, min(int(raw), 1440))
    except ValueError:
        return 10


def get_default_max_recovery_attempts() -> int:
    raw = os.getenv("OCTOPUS_DEFAULT_MAX_RECOVERY_ATTEMPTS", "2").strip()
    try:
        return max(0, min(int(raw), 10))
    except ValueError:
        return 2


def get_worker_max_concurrent_runs() -> int:
    raw = os.getenv("OCTOPUS_WORKER_MAX_CONCURRENT_RUNS", "1").strip()
    try:
        return max(1, min(int(raw), 8))
    except ValueError:
        return 1


def get_worker_poll_interval_seconds() -> float:
    raw = os.getenv("OCTOPUS_WORKER_POLL_INTERVAL_SECONDS", "0.25").strip()
    try:
        return max(0.05, min(float(raw), 5.0))
    except ValueError:
        return 0.25


def get_worker_per_agent_serialization_enabled() -> bool:
    raw = os.getenv("OCTOPUS_WORKER_PER_AGENT_SERIALIZATION", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def get_bridge_default_timeout_seconds() -> int:
    raw = os.getenv("OCTOPUS_BRIDGE_TIMEOUT_SECONDS", "180").strip()
    try:
        return max(1, min(int(raw), 900))
    except ValueError:
        return 180


def get_bridge_default_retry_limit() -> int:
    raw = os.getenv("OCTOPUS_BRIDGE_RETRY_LIMIT", "0").strip()
    try:
        return max(0, min(int(raw), 5))
    except ValueError:
        return 0


# ── P3 Governor kill switches ────────────────────────────────────────────────

def get_governor_enabled() -> bool:
    """Master kill switch: GOVERNOR_ENABLED=0 denies all actions."""
    raw = os.getenv("GOVERNOR_ENABLED", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def get_kanaloa_orchestrator_max_subtasks() -> int:
    raw = os.getenv("KANALOA_ORCHESTRATOR_MAX_SUBTASKS", "8").strip()
    try:
        return max(1, min(int(raw), 32))
    except ValueError:
        return 8


def get_kanaloa_orchestrator_max_attempts_per_subtask() -> int:
    raw = os.getenv("KANALOA_ORCHESTRATOR_MAX_ATTEMPTS", "2").strip()
    try:
        return max(1, min(int(raw), 5))
    except ValueError:
        return 2


def get_kanaloa_orchestrator_max_runtime_seconds() -> int:
    raw = os.getenv("KANALOA_ORCHESTRATOR_MAX_RUNTIME_SECONDS", "3600").strip()
    try:
        return max(30, min(int(raw), 86400))
    except ValueError:
        return 3600


def get_kanaloa_orchestrator_observe_poll_seconds() -> float:
    raw = os.getenv("KANALOA_ORCHESTRATOR_OBSERVE_POLL_SECONDS", "0.35").strip()
    try:
        return max(0.1, min(float(raw), 5.0))
    except ValueError:
        return 0.35


def get_kanaloa_orchestrator_observe_max_wait_seconds() -> float:
    raw = os.getenv("KANALOA_ORCHESTRATOR_OBSERVE_MAX_WAIT_SECONDS", "120").strip()
    try:
        return max(1.0, min(float(raw), 600.0))
    except ValueError:
        return 120.0


def get_governor_auto_execute_enabled() -> bool:
    """Auto-execution gate: GOVERNOR_AUTO_EXECUTE_ENABLED=1 allows low-risk auto runs.
    Default is OFF — all decisions require human confirmation unless explicitly enabled.
    """
    raw = os.getenv("GOVERNOR_AUTO_EXECUTE_ENABLED", "0").strip().lower()
    return raw not in {"0", "false", "no", "off"}
