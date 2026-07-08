from fastapi.testclient import TestClient

import app.main as bridge_main
from app.main import app


def test_health_ok():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_status_shape():
    client = TestClient(app)

    response = client.get("/v1/status")

    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "2.0.0"
    assert data["bridge_version"] == "2.0.0"
    assert "agents_registered" in data
    assert "handoff_dir" in data
    assert "results_count" in data


def test_adapter_probe_payload_uses_short_ttl_cache(monkeypatch):
    calls: list[str] = []

    def fake_which(command: str):
        calls.append(command)
        return f"C:\\fake\\{command}.exe"

    monkeypatch.setattr(bridge_main.shutil, "which", fake_which)
    bridge_main.clear_adapter_probe_cache()
    try:
        first = bridge_main._adapter_probe_payload()
        second = bridge_main._adapter_probe_payload()
    finally:
        bridge_main.clear_adapter_probe_cache()

    assert first == second
    assert first["codex_on_path"] is True
    assert calls == ["claude", "codex", "cursor"]


def test_cli_permission_error_is_reported_as_failed_diagnostic(monkeypatch):
    def fake_which(command: str):
        return f"C:\\fake\\{command}.exe"

    def fake_run(*_args, **_kwargs):
        raise PermissionError(5, "Access is denied", "codex")

    monkeypatch.setattr(bridge_main.shutil, "which", fake_which)
    monkeypatch.setattr(bridge_main.subprocess, "run", fake_run)

    payload = bridge_main.ExecutePayload(
        task_id="task_cli_permission",
        run_id="run_cli_permission",
        agent_id="agent_codex",
        adapter_id="codex_cli",
        title="Codex permission smoke",
        description="Do not modify source.",
    )

    result = bridge_main._channel_cli(payload, "hello", "codex", exec_subcommand="exec")

    assert result["ok"] is False
    assert result["error_type"] == "PermissionError"
    assert result["error_kind"] == "permission_denied"
    assert "Access is denied" in result["error"]
