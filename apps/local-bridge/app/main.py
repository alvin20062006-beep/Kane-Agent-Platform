from __future__ import annotations

import json
import os
import shutil
import subprocess
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


app = FastAPI(
    title="Octopus Local Bridge",
    version="0.2.0-beta",
    description="Beta Local Bridge: real HTTP execute + optional Claude CLI + handoff files + OpenClaw webhook + API callback.",
)

AGENTS: dict[str, AgentRegistration] = {}
HEARTBEATS: dict[str, Heartbeat] = {}
RESULTS: list[TaskResult] = []
LAST_EXECUTE: dict[str, str | None] = {"at": None, "last_error": None}


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return fallback
    return json.loads(text)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _persist_state() -> None:
    _write_json(AGENTS_FILE, [item.model_dump() for item in AGENTS.values()])
    _write_json(HEARTBEATS_FILE, [item.model_dump() for item in HEARTBEATS.values()])
    _write_json(RESULTS_FILE, [item.model_dump() for item in RESULTS[-200:]])
    _write_json(STATUS_FILE, LAST_EXECUTE)


def _load_state() -> None:
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
    for item in results:
        RESULTS.append(TaskResult.model_validate(item))

    LAST_EXECUTE.update({"at": status.get("at"), "last_error": status.get("last_error")})


_load_state()


def _bridge_key() -> str | None:
    v = os.getenv("OCTOPUS_BRIDGE_SHARED_SECRET")
    return v.strip() if v else None


def _api_base() -> str:
    return os.getenv("OCTOPUS_API_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")


def _openclaw_url() -> str | None:
    u = os.getenv("OPENCLAW_WEBHOOK_URL")
    return u.strip() if u else None


def _try_run(cmd: list[str], timeout: float) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out[:24000], out


@app.get("/health")
def health():
    return {"status": "ok", "service": "local-bridge", "beta": True}


@app.get("/v1/status")
def status():
    return {
        "beta": True,
        "agents_registered": len(AGENTS),
        "heartbeats": len(HEARTBEATS),
        "last_execute": LAST_EXECUTE,
        "handoff_dir": str(HANDOFF_DIR),
        "openclaw_configured": bool(_openclaw_url()),
        "claude_on_path": bool(shutil.which("claude")),
        "cursor_on_path": bool(shutil.which("cursor")),
        "last_heartbeat_at": max((hb.ts for hb in HEARTBEATS.values()), default=None),
        "results_count": len(RESULTS),
    }


@app.post("/agents/register")
def register_agent(
    payload: AgentRegistration,
    x_octopus_bridge_key: str | None = Header(default=None, alias="X-Octopus-Bridge-Key"),
):
    secret = _bridge_key()
    if secret and x_octopus_bridge_key != secret:
        raise HTTPException(status_code=401, detail="bridge_auth_failed")
    AGENTS[payload.agent_id] = payload
    _persist_state()
    return {"ok": True, "beta": True, "data": payload}


@app.post("/agents/heartbeat")
def heartbeat(payload: Heartbeat):
    HEARTBEATS[payload.agent_id] = payload
    _persist_state()
    return {"ok": True, "beta": True, "data": payload}


@app.get("/agents")
def list_agents():
    return {
        "beta": True,
        "agents": list(AGENTS.values()),
        "heartbeats": list(HEARTBEATS.values()),
    }


@app.get("/agents/{agent_id}")
def get_agent(agent_id: str):
    agent = AGENTS.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="agent_not_found")
    return {
        "beta": True,
        "agent": agent,
        "heartbeat": HEARTBEATS.get(agent_id),
        "recent_results": [r for r in RESULTS if r.agent_id == agent_id][-10:],
    }


@app.post("/v1/execute")
def execute(
    payload: ExecutePayload,
    x_octopus_bridge_key: str | None = Header(default=None, alias="X-Octopus-Bridge-Key"),
):
    """
    Synchronous execute invoked by Octopus API.
    Honest behavior:
    - claude_code: runs `claude` CLI if installed; otherwise handoff file.
    - cursor_cli: writes handoff markdown (truthful: no guaranteed headless Cursor automation).
    - openclaw_http: POST JSON to OPENCLAW_WEBHOOK_URL if set; otherwise handoff.
    """
    secret = _bridge_key()
    if secret and x_octopus_bridge_key != secret:
        raise HTTPException(status_code=401, detail="bridge_auth_failed")

    LAST_EXECUTE["at"] = _now_iso()
    LAST_EXECUTE["last_error"] = None
    _persist_state()

    adapter = payload.adapter_id
    prompt = f"{payload.title}\n\n{payload.description or ''}".strip()
    api_profile = payload.api_profile or None

    # 1) Claude Code CLI (strongest truthful automation when installed)
    if adapter == "claude_code":
        cli = shutil.which("claude")
        if cli:
            try:
                # Claude Code supports non-interactive prompts via -p in many installs.
                code, combined, _full = _try_run([cli, "-p", prompt], timeout=120.0)
                if code == 0:
                    return {
                        "ok": True,
                        "beta": True,
                        "integration_path": "claude_cli",
                        "output": combined,
                        "error": None,
                    }
                return {
                    "ok": False,
                    "beta": True,
                    "integration_path": "claude_cli",
                    "output": combined,
                    "error": f"claude_cli_exit_{code}",
                }
            except Exception as e:  # noqa: BLE001
                LAST_EXECUTE["last_error"] = str(e)
                _persist_state()
                return {
                    "ok": False,
                    "beta": True,
                    "integration_path": "claude_cli",
                    "output": None,
                    "error": str(e),
                }

        path = HANDOFF_DIR / f"{payload.task_id}_{payload.run_id}.md"
        body = (
            "# Octopus → Claude Code handoff\n\n"
            f"- task_id: `{payload.task_id}`\n"
            f"- run_id: `{payload.run_id}`\n"
            f"- agent_id: `{payload.agent_id}`\n\n"
            f"- api_profile: `{json.dumps(api_profile, ensure_ascii=False) if api_profile else 'null'}`\n\n"
            "## Prompt\n\n"
            f"{prompt}\n\n"
            "## After you finish in Claude Code\n\n"
            "Post results back to Octopus API:\n\n"
            f"POST `{_api_base()}/integrations/bridge/complete`\n\n"
            "```json\n"
            "{\n"
            f'  "task_id": "{payload.task_id}",\n'
            f'  "run_id": "{payload.run_id}",\n'
            '  "status": "succeeded",\n'
            '  "output": "paste summary here",\n'
            '  "error": null,\n'
            '  "integration_path": "manual_claude_code"\n'
            "}\n"
            "```\n"
        )
        path.write_text(body, encoding="utf-8")
        return {
            "ok": True,
            "beta": True,
            "integration_path": "claude_handoff_file",
            "output": f"Wrote handoff: {path}. Install Claude Code CLI for automated `claude -p` execution.",
            "error": None,
            "handoff_path": str(path),
        }

    # 2) OpenClaw HTTP ingest (real when URL is configured)
    if adapter == "openclaw_http":
        url = _openclaw_url()
        if url:
            try:
                r = httpx.post(
                    url,
                    json={
                        "source": "octopus_platform",
                        "task_id": payload.task_id,
                        "run_id": payload.run_id,
                        "agent_id": payload.agent_id,
                        "title": payload.title,
                        "description": payload.description,
                        "execution_mode": payload.execution_mode,
                        "text": prompt,
                    },
                    timeout=30.0,
                )
                text = r.text[:8000]
                if r.status_code >= 400:
                    return {
                        "ok": False,
                        "beta": True,
                        "integration_path": "openclaw_http",
                        "output": text,
                        "error": f"openclaw_http_{r.status_code}",
                    }
                return {
                    "ok": True,
                    "beta": True,
                    "integration_path": "openclaw_http",
                    "output": text or "OpenClaw accepted payload (empty body).",
                    "error": None,
                }
            except Exception as e:  # noqa: BLE001
                LAST_EXECUTE["last_error"] = str(e)
                _persist_state()
                return {
                    "ok": False,
                    "beta": True,
                    "integration_path": "openclaw_http",
                    "output": None,
                    "error": str(e),
                }

        path = HANDOFF_DIR / f"{payload.task_id}_{payload.run_id}_openclaw.md"
        path.write_text(
            "# Octopus → OpenClaw handoff\n\n"
            f"{prompt}\n\n"
            "Configure `OPENCLAW_WEBHOOK_URL` on Local Bridge to enable HTTP ingest.\n",
            encoding="utf-8",
        )
        return {
            "ok": True,
            "beta": True,
            "integration_path": "openclaw_handoff_file",
            "output": f"Wrote handoff: {path}. Set OPENCLAW_WEBHOOK_URL for real HTTP delivery.",
            "error": None,
            "handoff_path": str(path),
        }

    # 3b) Local script / command runner (Embedded on Bridge host; Beta)
    if adapter == "local_script":
        cp = payload.agent_control_plane or {}
        cmd = cp.get("shell_command")
        if not cmd:
            cmd = prompt or None
        if not cmd:
            LAST_EXECUTE["last_error"] = "missing_shell_command"
            _persist_state()
            return {
                "ok": False,
                "beta": True,
                "integration_path": "local_script",
                "output": None,
                "error": "missing_shell_command: set control_plane.shell_command on the agent or put a command in the task description",
            }
        cwd = cp.get("working_directory") or None
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
                "beta": True,
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
                "beta": True,
                "integration_path": "local_script",
                "output": out[:24000],
                "error": None if ok else f"exit_{p.returncode}",
            }
        except Exception as e:  # noqa: BLE001
            LAST_EXECUTE["last_error"] = str(e)
            _persist_state()
            return {
                "ok": False,
                "beta": True,
                "integration_path": "local_script",
                "output": None,
                "error": str(e),
            }

    # 3) Cursor: truthful handoff (no fake full automation)
    if adapter == "cursor_cli":
        path = HANDOFF_DIR / f"{payload.task_id}_{payload.run_id}_cursor.md"
        path.write_text(
            "# Octopus → Cursor handoff\n\n"
            f"{prompt}\n\n"
            "## Beta limitation\n\n"
            "Cursor does not expose a single guaranteed headless task runner across all installs.\n"
            "Use Cursor Composer/Agent with this prompt, then submit results via:\n\n"
            f"POST `{_api_base()}/integrations/bridge/complete`\n",
            encoding="utf-8",
        )
        cursor = shutil.which("cursor")
        note = f"Wrote handoff: {path}."
        if cursor:
            code, combined, _ = _try_run([cursor, "--version"], timeout=10.0)
            note += f" Detected `cursor` on PATH (version probe exit={code}). Output:\n{combined[:2000]}"
        else:
            note += " `cursor` CLI not found on PATH (handoff still created)."
        return {
            "ok": True,
            "beta": True,
            "integration_path": "cursor_handoff_file",
            "output": note,
            "error": None,
            "handoff_path": str(path),
        }

    return {
        "ok": False,
        "beta": True,
        "integration_path": "unknown_adapter",
        "output": None,
        "error": f"unsupported_adapter:{adapter}",
    }


@app.post("/tasks/result")
def submit_result(payload: TaskResult):
    RESULTS.append(payload)
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
    return {"ok": True, "beta": True, "data": payload}


@app.get("/tasks/results")
def list_results():
    return {"beta": True, "items": RESULTS[-50:]}
