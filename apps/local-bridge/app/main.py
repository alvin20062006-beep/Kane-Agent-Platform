from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
HANDOFF_DIR = DATA_ROOT / "handoffs"
HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
AGENTS_FILE = DATA_ROOT / "agents.json"
HEARTBEATS_FILE = DATA_ROOT / "heartbeats.json"
RESULTS_FILE = DATA_ROOT / "results.json"
STATUS_FILE = DATA_ROOT / "status.json"


class Heartbeat(BaseModel):
    agent_id: str
    status: str = "unknown"
    ts: str = Field(default_factory=_now_iso)


class AgentRegistration(BaseModel):
    agent_id: str
    display_name: str
    adapter_id: str
    capabilities: dict[str, bool] = Field(default_factory=dict)


class TaskResult(BaseModel):
    task_id: str
    run_id: str | None = None
    agent_id: str
    status: str
    output: str | None = None
    ts: str = Field(default_factory=_now_iso)


class ExecutePayload(BaseModel):
    task_id: str
    run_id: str
    agent_id: str
    adapter_id: str
    title: str
    description: str | None = None
    execution_mode: str | None = None
    api_profile: dict[str, Any] | None = None
    agent_control_plane: dict[str, Any] | None = None


BRIDGE_VERSION = "2.0.0"
_SUPPORTED_ADAPTERS = [
    "claude_code",
    "codex_cli",
    "cursor_cli",
    "openclaw_http",
    "local_script",
    "http_agent",
    "cli_agent",
]

app = FastAPI(
    title="Kane Local Bridge",
    version="2.0.0",
    description="Kane local execution adapter: POST /v1/execute (Claude CLI, Codex CLI, OpenClaw webhook, handoff files, local_script, Cursor handoff) + API callback.",
)

AGENTS: dict[str, AgentRegistration] = {}
HEARTBEATS: dict[str, Heartbeat] = {}
RESULTS: list[TaskResult] = []
LAST_EXECUTE: dict[str, Any] = {"at": None, "last_error": None}
STATE_LOCK = threading.RLock()
_ADAPTER_PROBE_TTL_SECONDS = 2.0
_ADAPTER_PROBE_LOCK = threading.RLock()
_ADAPTER_PROBE_CACHE: tuple[float, dict[str, Any]] | None = None


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return fallback
    return json.loads(text)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    last_err: Exception | None = None
    for attempt in range(8):
        try:
            os.replace(tmp, path)
            last_err = None
            break
        except (PermissionError, OSError) as err:
            last_err = err
            time.sleep(0.05 * (attempt + 1))
    if last_err:
        raise last_err


def _persist_state() -> None:
    with STATE_LOCK:
        _write_json(AGENTS_FILE, [item.model_dump() for item in AGENTS.values()])
        _write_json(HEARTBEATS_FILE, [item.model_dump() for item in HEARTBEATS.values()])
        _write_json(RESULTS_FILE, [item.model_dump() for item in RESULTS[-200:]])
        _write_json(STATUS_FILE, LAST_EXECUTE)


def _load_state() -> None:
    with STATE_LOCK:
        agents = _read_json(AGENTS_FILE, [])
        heartbeats = _read_json(HEARTBEATS_FILE, [])
        results = _read_json(RESULTS_FILE, [])
        status = _read_json(STATUS_FILE, LAST_EXECUTE)

        AGENTS.clear()
        for item in agents:
            reg = AgentRegistration.model_validate(item)
            AGENTS[reg.agent_id] = reg

        HEARTBEATS.clear()
        for item in heartbeats:
            hb = Heartbeat.model_validate(item)
            HEARTBEATS[hb.agent_id] = hb

        RESULTS.clear()
        for item in results[-200:]:
            RESULTS.append(TaskResult.model_validate(item))

        LAST_EXECUTE.clear()
        if isinstance(status, dict):
            LAST_EXECUTE.update(status)
        LAST_EXECUTE.setdefault("at", None)
        LAST_EXECUTE.setdefault("last_error", None)


_load_state()


def _bridge_key() -> str | None:
    v = os.getenv("OCTOPUS_BRIDGE_SHARED_SECRET")
    return v.strip() if v else None


def _require_bridge_key(x_octopus_bridge_key: str | None) -> None:
    secret = _bridge_key()
    if secret and x_octopus_bridge_key != secret:
        raise HTTPException(status_code=401, detail="bridge_auth_failed")


def _safe_api_profile_ref(profile: dict[str, Any] | None) -> dict[str, Any] | None:
    if not profile:
        return None
    return {
        k: profile[k]
        for k in ("profile_id", "provider", "base_url", "model")
        if k in profile and profile[k] is not None
    }


def _workspace_root() -> Path | None:
    raw = (os.getenv("OCTOPUS_BRIDGE_WORKSPACE_ROOT") or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def _cwd_allowed(cwd: str | None) -> bool:
    if not cwd:
        return True
    root = _workspace_root()
    if not root:
        return True
    try:
        resolved = Path(cwd).expanduser().resolve()
        resolved.relative_to(root)
        return True
    except ValueError:
        return False


def _api_base() -> str:
    return os.getenv("OCTOPUS_API_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")


def _openclaw_url() -> str | None:
    u = os.getenv("OPENCLAW_WEBHOOK_URL")
    return u.strip() if u else None


def _claude_command() -> str:
    return (os.getenv("CLAUDE_CODE_COMMAND") or "claude").strip() or "claude"


def _codex_command() -> str:
    return (os.getenv("CODEX_COMMAND") or "codex").strip() or "codex"


def _try_run(cmd: list[str], timeout: float) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out[:24000], out


def _record_last_execute(**updates: Any) -> None:
    with STATE_LOCK:
        LAST_EXECUTE.update(updates)
    _persist_state()


def _adapter_probe_payload() -> dict[str, Any]:
    global _ADAPTER_PROBE_CACHE

    now = time.monotonic()
    with _ADAPTER_PROBE_LOCK:
        if _ADAPTER_PROBE_CACHE is not None:
            cached_at, cached_payload = _ADAPTER_PROBE_CACHE
            if now - cached_at <= _ADAPTER_PROBE_TTL_SECONDS:
                return deepcopy(cached_payload)

        payload = {
            "bridge_version": BRIDGE_VERSION,
            "claude_on_path": bool(shutil.which(_claude_command().split()[0])),
            "codex_on_path": bool(shutil.which(_codex_command().split()[0])),
            "cursor_on_path": bool(shutil.which("cursor")),
            "openclaw_configured": bool(_openclaw_url()),
            "supported_adapters": list(_SUPPORTED_ADAPTERS),
        }
        _ADAPTER_PROBE_CACHE = (time.monotonic(), deepcopy(payload))
        return payload


def clear_adapter_probe_cache() -> None:
    global _ADAPTER_PROBE_CACHE
    with _ADAPTER_PROBE_LOCK:
        _ADAPTER_PROBE_CACHE = None


def _status_snapshot() -> dict[str, Any]:
    with STATE_LOCK:
        return {
            "agents_registered": len(AGENTS),
            "heartbeats": len(HEARTBEATS),
            "last_execute": dict(LAST_EXECUTE),
            "handoff_dir": str(HANDOFF_DIR),
            "last_heartbeat_at": max((hb.ts for hb in HEARTBEATS.values()), default=None),
            "results_count": len(RESULTS),
        }


def _status_payload() -> dict[str, Any]:
    return {
        "version": BRIDGE_VERSION,
        **_adapter_probe_payload(),
        **_status_snapshot(),
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "kane-local-bridge", "version": BRIDGE_VERSION, **_adapter_probe_payload()}


@app.get("/v1/status")
def status():
    return _status_payload()


@app.post("/agents/register")
def register_agent(
    payload: AgentRegistration,
    x_octopus_bridge_key: str | None = Header(default=None, alias="X-Octopus-Bridge-Key"),
):
    _require_bridge_key(x_octopus_bridge_key)
    with STATE_LOCK:
        AGENTS[payload.agent_id] = payload
    _persist_state()
    return {"ok": True, "version": BRIDGE_VERSION, "data": payload}


@app.post("/agents/heartbeat")
def heartbeat(
    payload: Heartbeat,
    x_octopus_bridge_key: str | None = Header(default=None, alias="X-Octopus-Bridge-Key"),
):
    _require_bridge_key(x_octopus_bridge_key)
    with STATE_LOCK:
        HEARTBEATS[payload.agent_id] = payload
    _persist_state()
    return {"ok": True, "version": BRIDGE_VERSION, "data": payload}


@app.get("/agents")
def list_agents(x_octopus_bridge_key: str | None = Header(default=None, alias="X-Octopus-Bridge-Key")):
    _require_bridge_key(x_octopus_bridge_key)
    with STATE_LOCK:
        return {
            "version": BRIDGE_VERSION,
            "agents": list(AGENTS.values()),
            "heartbeats": list(HEARTBEATS.values()),
        }


@app.get("/agents/{agent_id}")
def get_agent(agent_id: str, x_octopus_bridge_key: str | None = Header(default=None, alias="X-Octopus-Bridge-Key")):
    _require_bridge_key(x_octopus_bridge_key)
    with STATE_LOCK:
        agent = AGENTS.get(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="agent_not_found")
        return {
            "version": BRIDGE_VERSION,
            "agent": agent,
            "heartbeat": HEARTBEATS.get(agent_id),
            "recent_results": [r for r in RESULTS if r.agent_id == agent_id][-10:],
        }


def _cp_get(payload: ExecutePayload, key: str) -> Any:
    cp = payload.agent_control_plane or {}
    return cp.get(key) if isinstance(cp, dict) else None


def _write_handoff_file(payload: ExecutePayload, prompt: str, vendor: str, suffix: str, extra: str = "") -> Path:
    """Universal handoff: works for any agent (IDE, web UI, manual)."""
    callback_url = f"{_api_base()}/integrations/bridge/complete"
    integration_path = f"manual_{payload.adapter_id}"
    path = HANDOFF_DIR / f"{payload.task_id}_{payload.run_id}{suffix}.md"
    frontmatter = (
        "---\n"
        f'task_id: "{payload.task_id}"\n'
        f'run_id: "{payload.run_id}"\n'
        f'agent_id: "{payload.agent_id}"\n'
        f'adapter_id: "{payload.adapter_id}"\n'
        f'callback_url: "{callback_url}"\n'
        f'integration_path: "{integration_path}"\n'
        "completion_mode: handoff_callback\n"
        "schema_version: \"1.0\"\n"
        "---\n\n"
    )
    body = frontmatter + (
        f"# Kane -> {vendor} handoff\n\n"
        f"- task_id: `{payload.task_id}`\n"
        f"- run_id: `{payload.run_id}`\n"
        f"- agent_id: `{payload.agent_id}`\n"
        f"- adapter_id: `{payload.adapter_id}`\n"
        f"- callback_url: `{callback_url}`\n\n"
        "## Prompt\n\n"
        f"{prompt}\n\n"
        f"{extra}"
        "## After you finish\n\n"
        f"POST `{callback_url}`\n\n"
        "```json\n"
        "{\n"
        f'  "task_id": "{payload.task_id}",\n'
        f'  "run_id": "{payload.run_id}",\n'
        '  "status": "succeeded",\n'
        '  "output": "paste summary here",\n'
        '  "error": null,\n'
        f'  "integration_path": "manual_{payload.adapter_id}"\n'
        "}\n"
        "```\n"
    )
    path.write_text(body, encoding="utf-8")
    return path


def _channel_http(payload: ExecutePayload, prompt: str, url: str) -> dict[str, Any]:
    """Universal HTTP channel: POST the task to any agent webhook."""
    started = time.perf_counter()
    try:
        r = httpx.post(
            url,
            json={
                "source": "kane_agent_platform",
                "task_id": payload.task_id,
                "run_id": payload.run_id,
                "agent_id": payload.agent_id,
                "adapter_id": payload.adapter_id,
                "title": payload.title,
                "description": payload.description,
                "execution_mode": payload.execution_mode,
                "text": prompt,
                "api_profile": _safe_api_profile_ref(payload.api_profile),
                "callback_url": f"{_api_base()}/integrations/bridge/complete",
            },
            timeout=30.0,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        text = r.text[:8000]
        if r.status_code >= 400:
            return {"ok": False, "version": BRIDGE_VERSION, "integration_path": "http_agent",
                    "output": text, "error": f"http_agent_{r.status_code}",
                    "http_status_code": r.status_code, "elapsed_ms": elapsed_ms,
                    "output_excerpt": text[:2000] if text else None}
        return {"ok": True, "version": BRIDGE_VERSION, "integration_path": "http_agent",
                "output": text or "Agent webhook accepted payload (empty body).", "error": None,
                "http_status_code": r.status_code, "elapsed_ms": elapsed_ms}
    except Exception as e:  # noqa: BLE001
        _record_last_execute(last_error=str(e), last_error_type=type(e).__name__)
        return {"ok": False, "version": BRIDGE_VERSION, "integration_path": "http_agent", "output": None, "error": str(e)}


def _channel_cli(payload: ExecutePayload, prompt: str, command: str, *, exec_subcommand: str | None = None) -> dict[str, Any]:
    """Universal CLI channel: run any command-line agent with the prompt."""
    import shlex

    posix = os.name != "nt"
    try:
        base = shlex.split(str(command), posix=posix)
    except ValueError:
        base = str(command).split()
    if not base:
        return {"ok": False, "version": BRIDGE_VERSION, "integration_path": "cli_agent",
                "output": None, "error": "could_not_parse_cli_command"}
    bin0 = base[0]
    if not shutil.which(bin0) and not os.path.exists(bin0):
        return {"ok": False, "version": BRIDGE_VERSION, "integration_path": "cli_agent",
                "output": None, "error": f"cli_not_found:{bin0}"}
    argv = base + ([exec_subcommand] if exec_subcommand else []) + [prompt]
    run_env = os.environ.copy()
    for k, v in (_cp_get(payload, "env") or {}).items():
        run_env[str(k)] = str(v)
    cwd = _cp_get(payload, "working_directory") or None
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=120.0, cwd=cwd or None, env=run_env)
        out = (p.stdout or "") + (p.stderr or "")
        ok = p.returncode == 0
        return {"ok": ok, "version": BRIDGE_VERSION, "integration_path": "cli_agent",
                "output": out[:24000], "error": None if ok else f"cli_exit_{p.returncode}",
                "error_type": None if ok else "ProcessExit", "exit_code": p.returncode}
    except Exception as e:  # noqa: BLE001
        error_type = type(e).__name__
        winerror = getattr(e, "winerror", None)
        errno = getattr(e, "errno", None)
        error_kind = "permission_denied" if isinstance(e, PermissionError) or winerror == 5 else "cli_launch_error"
        diagnostic_hint = (
            "The CLI was found but Windows denied execution. Check file permissions, execution policy, antivirus controls, and whether the CLI can run in this shell."
            if error_kind == "permission_denied"
            else "The CLI could not be launched by Local Bridge. Check the configured command and working directory."
        )
        error_text = f"{error_type}: {e}"
        _record_last_execute(
            status="failed",
            integration_path="cli_agent",
            last_error=error_text,
            last_error_type=error_type,
            error_kind=error_kind,
        )
        return {
            "ok": False,
            "version": BRIDGE_VERSION,
            "integration_path": "cli_agent",
            "output": None,
            "error": error_text,
            "error_type": error_type,
            "error_kind": error_kind,
            "winerror": winerror,
            "errno": errno,
            "diagnostic_hint": diagnostic_hint,
        }


def _track_execute_error(res: dict[str, Any]) -> None:
    if res.get("ok"):
        _record_last_execute(status="succeeded", integration_path=res.get("integration_path"), last_error=None)
        return
    _record_last_execute(
        status="failed",
        integration_path=res.get("integration_path"),
        last_error=res.get("error"),
        last_error_type=res.get("error_type"),
        error_kind=res.get("error_kind"),
        http_status_code=res.get("http_status_code"),
        elapsed_ms=res.get("elapsed_ms"),
        output_excerpt=res.get("output_excerpt") or ((res.get("output") or "")[:2000] if res.get("output") else None),
    )


def _run_cli_preset(
    payload: ExecutePayload,
    prompt: str,
    *,
    command: str,
    integration_path: str,
    handoff_path_label: str,
    handoff_suffix: str,
    vendor: str,
    exec_subcommand: str | None = None,
    handoff_extra: str = "",
    install_hint: str,
) -> dict[str, Any]:
    """Vendor preset on top of the generic CLI channel (claude -p, codex exec, etc.)."""
    bin0 = command.split()[0]
    if shutil.which(bin0) or os.path.exists(bin0):
        res = _channel_cli(payload, prompt, command, exec_subcommand=exec_subcommand)
        out = {**res, "integration_path": integration_path}
        _track_execute_error(out)
        return out
    path = _write_handoff_file(payload, prompt, vendor, handoff_suffix, extra=handoff_extra)
    return {
        "ok": True,
        "version": BRIDGE_VERSION,
        "integration_path": handoff_path_label,
        "output": f"Wrote handoff: {path}. {install_hint}",
        "error": None,
        "handoff_path": str(path),
    }


@app.post("/v1/execute")
def execute(
    payload: ExecutePayload,
    x_octopus_bridge_key: str | None = Header(default=None, alias="X-Octopus-Bridge-Key"),
):
    """
    Synchronous execute invoked by Kane API.
    Honest behavior:
    - claude_code: runs `claude` CLI if installed; otherwise handoff file.
    - cursor_cli: writes handoff markdown (truthful: no guaranteed headless Cursor automation).
    - openclaw_http: POST JSON to OPENCLAW_WEBHOOK_URL if set; otherwise handoff.
    """
    secret = _bridge_key()
    if secret and x_octopus_bridge_key != secret:
        raise HTTPException(status_code=401, detail="bridge_auth_failed")

    with STATE_LOCK:
        LAST_EXECUTE.clear()
        LAST_EXECUTE.update(
            {
                "at": _now_iso(),
                "phase": "received",
                "task_id": payload.task_id,
                "run_id": payload.run_id,
                "agent_id": payload.agent_id,
                "adapter_id": payload.adapter_id,
                "last_error": None,
            }
        )
    _persist_state()

    adapter = payload.adapter_id
    prompt = f"{payload.title}\n\n{payload.description or ''}".strip()
    api_profile = payload.api_profile or None

    # Vendor presets (thin wrappers on generic CLI / HTTP / handoff channels)
    if adapter == "claude_code":
        api_extra = ""
        if payload.api_profile:
            ref = _safe_api_profile_ref(payload.api_profile)
            if ref:
                api_extra = f"- api_profile_id: `{ref.get('profile_id', 'n/a')}` (provider={ref.get('provider', 'n/a')})\n\n"
        return _run_cli_preset(
            payload,
            prompt,
            command=_claude_command(),
            integration_path="claude_cli",
            handoff_path_label="claude_handoff_file",
            handoff_suffix="",
            vendor="Claude Code",
            exec_subcommand="-p",
            handoff_extra=api_extra,
            install_hint="Install Claude Code CLI for automated `claude -p` execution.",
        )

    if adapter == "codex_cli":
        return _run_cli_preset(
            payload,
            prompt,
            command=_codex_command(),
            integration_path="codex_cli",
            handoff_path_label="codex_handoff_file",
            handoff_suffix="_codex",
            vendor="Codex",
            exec_subcommand="exec",
            handoff_extra="Install the Codex CLI (or set CODEX_COMMAND) for automated `codex exec` execution.\n\n",
            install_hint="Install Codex CLI for automated `codex exec` execution.",
        )

    # HTTP channel: OpenClaw or any per-agent webhook
    if adapter in ("openclaw_http", "http_agent"):
        url = _cp_get(payload, "webhook_url") or (_openclaw_url() if adapter == "openclaw_http" else None)
        if url:
            res = _channel_http(payload, prompt, url)
            _track_execute_error(res)
            return res

        vendor = "OpenClaw" if adapter == "openclaw_http" else "HTTP agent"
        path = _write_handoff_file(
            payload,
            prompt,
            vendor,
            "_http_agent",
            extra=(
                "## Enable HTTP delivery\n\n"
                "Set this agent's `control_plane.webhook_url` (per-agent) "
                "or `OPENCLAW_WEBHOOK_URL` on the Bridge host.\n\n"
            ),
        )
        return {
            "ok": True,
            "version": BRIDGE_VERSION,
            "integration_path": "http_agent_handoff_file",
            "output": f"Wrote handoff: {path}. Set control_plane.webhook_url for real HTTP delivery.",
            "error": None,
            "handoff_path": str(path),
        }

    # 2b) CLI channel: any command-line agent via control_plane.cli_path (multi-agent generic)
    if adapter == "cli_agent":
        command = _cp_get(payload, "cli_path") or _cp_get(payload, "shell_command")
        if command:
            res = _channel_cli(payload, prompt, str(command))
            _track_execute_error(res)
            return res
        path = _write_handoff_file(
            payload,
            prompt,
            "CLI agent",
            "_cli_agent",
            extra="## Enable CLI execution\n\nSet this agent's `control_plane.cli_path` to the command to run.\n\n",
        )
        return {
            "ok": True,
            "version": BRIDGE_VERSION,
            "integration_path": "cli_agent_handoff_file",
            "output": f"Wrote handoff: {path}. Set control_plane.cli_path for automated CLI execution.",
            "error": None,
            "handoff_path": str(path),
        }

    # 3b) Local script / command runner (on Bridge host)
    if adapter == "local_script":
        cp = payload.agent_control_plane or {}
        if not cp.get("allow_local_script"):
            return {
                "ok": False,
                "version": BRIDGE_VERSION,
                "integration_path": "local_script",
                "output": None,
                "error": "local_script_disabled: set control_plane.allow_local_script=true on the agent",
            }
        cmd = cp.get("shell_command")
        if not cmd:
            cmd = prompt or None
        if not cmd:
            with STATE_LOCK:
                LAST_EXECUTE["last_error"] = "missing_shell_command"
            _persist_state()
            return {
                "ok": False,
                "version": BRIDGE_VERSION,
                "integration_path": "local_script",
                "output": None,
                "error": "missing_shell_command: set control_plane.shell_command on the agent or put a command in the task description",
            }
        cwd = cp.get("working_directory") or None
        if not _cwd_allowed(str(cwd) if cwd else None):
            return {
                "ok": False,
                "version": BRIDGE_VERSION,
                "integration_path": "local_script",
                "output": None,
                "error": "working_directory_outside_bridge_workspace_root",
            }
        run_env = os.environ.copy()
        for k, v in (cp.get("env") or {}).items():
            run_env[str(k)] = str(v)
        import shlex

        posix = os.name != "nt"
        try:
            parts = shlex.split(str(cmd), posix=posix) if isinstance(cmd, str) else []
        except ValueError:
            parts = str(cmd).split()
        if not parts:
            return {
                "ok": False,
                "version": BRIDGE_VERSION,
                "integration_path": "local_script",
                "output": None,
                "error": "could_not_parse_shell_command",
            }
        try:
            p = subprocess.run(
                parts,
                capture_output=True,
                text=True,
                timeout=120.0,
                cwd=cwd or None,
                env=run_env,
            )
            out = (p.stdout or "") + (p.stderr or "")
            ok = p.returncode == 0
            return {
                "ok": ok,
                "version": BRIDGE_VERSION,
                "integration_path": "local_script",
                "output": out[:24000],
                "error": None if ok else f"exit_{p.returncode}",
            }
        except Exception as e:  # noqa: BLE001
            _record_last_execute(status="failed", integration_path="local_script", last_error=str(e), last_error_type=type(e).__name__)
            return {
                "ok": False,
                "version": BRIDGE_VERSION,
                "integration_path": "local_script",
                "output": None,
                "error": str(e),
            }

    # Cursor: handoff-only preset (IDE-assisted, no headless automation)
    if adapter == "cursor_cli":
        path = _write_handoff_file(
            payload,
            prompt,
            "Cursor",
            "_cursor",
            extra=(
                "## Known limitation\n\n"
                "Cursor does not expose a single guaranteed headless task runner across all installs.\n"
                "Use Cursor Composer/Agent with this prompt, then submit results via the callback above.\n\n"
            ),
        )
        note = f"Wrote handoff: {path}."
        cursor = shutil.which("cursor")
        if cursor:
            code, combined, _ = _try_run([cursor, "--version"], timeout=10.0)
            note += f" Detected `cursor` on PATH (version probe exit={code}). Output:\n{combined[:2000]}"
        else:
            note += " `cursor` CLI not found on PATH (handoff still created)."
        return {
            "ok": True,
            "version": BRIDGE_VERSION,
            "integration_path": "cursor_handoff_file",
            "output": note,
            "error": None,
            "handoff_path": str(path),
        }

    # Catch-all: ANY other adapter still connects via the best available channel.
    # Multi-agent platform contract — no agent is rejected as "unsupported".
    webhook = _cp_get(payload, "webhook_url")
    if webhook:
        res = _channel_http(payload, prompt, str(webhook))
        _track_execute_error(res)
        return res

    command = _cp_get(payload, "cli_path") or _cp_get(payload, "shell_command")
    if command:
        res = _channel_cli(payload, prompt, str(command))
        _track_execute_error(res)
        return res

    path = _write_handoff_file(
        payload,
        prompt,
        adapter or "agent",
        f"_{adapter or 'agent'}",
        extra=(
            "## Connect this agent\n\n"
            "Provide one of the following on the agent's `control_plane`:\n"
            "- `webhook_url` for HTTP delivery\n"
            "- `cli_path` for command-line execution\n"
            "Otherwise complete the task manually and post the callback below.\n\n"
        ),
    )
    return {
        "ok": True,
        "version": BRIDGE_VERSION,
        "integration_path": "generic_handoff_file",
        "output": f"Wrote handoff: {path}. Set control_plane.webhook_url or cli_path to automate adapter '{adapter}'.",
        "error": None,
        "handoff_path": str(path),
    }


@app.post("/tasks/result")
def submit_result(
    payload: TaskResult,
    x_octopus_bridge_key: str | None = Header(default=None, alias="X-Octopus-Bridge-Key"),
):
    _require_bridge_key(x_octopus_bridge_key)
    with STATE_LOCK:
        RESULTS.append(payload)
        del RESULTS[:-200]
    _persist_state()
    if payload.run_id:
        try:
            headers = {}
            secret = _bridge_key()
            if secret:
                headers["X-Octopus-Bridge-Key"] = secret
            httpx.post(
                f"{_api_base()}/integrations/bridge/complete",
                json={
                    "task_id": payload.task_id,
                    "run_id": payload.run_id,
                    "status": "succeeded" if payload.status == "succeeded" else "failed",
                    "output": payload.output,
                    "error": None if payload.status == "succeeded" else payload.output,
                    "integration_path": "bridge_tasks_result",
                },
                headers=headers,
                timeout=10.0,
            )
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "version": BRIDGE_VERSION, "data": payload}


@app.get("/tasks/results")
def list_results(x_octopus_bridge_key: str | None = Header(default=None, alias="X-Octopus-Bridge-Key")):
    _require_bridge_key(x_octopus_bridge_key)
    with STATE_LOCK:
        return {"version": BRIDGE_VERSION, "items": RESULTS[-50:]}
