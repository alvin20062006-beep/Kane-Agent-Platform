from __future__ import annotations

import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.main import app, create_app
from app.security.url_safety import is_safe_http_url
from app.store.sqlite_store import SQLiteStore


def test_api_imports_and_creates_app():
    assert app.title == "Kane Agent Platform API"
    assert app.version == "3.0.1-beta"


def test_default_lifespan_starts_without_vendor_specific_external_adapters():
    fresh_app = create_app()
    fresh_app.state.store = SQLiteStore(":memory:")
    with TestClient(fresh_app) as client:
        assert client.get("/health").status_code == 200
        assert fresh_app.state.coordinator.has_adapter("kanaloa")
        assert set(fresh_app.state.coordinator._adapters) == {"kanaloa"}
        assert fresh_app.state.kanaloa_adapter.runtime is fresh_app.state.kanaloa_runtime


def test_health_endpoint_responds_honestly():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "kane-agent-platform-api"
    assert body["version"] == "3.0.1-beta"
    assert "startup" in body

    # Confirm no legacy task/run/watchdog/diagnostics fields
    assert "tasks_total" not in body
    assert "runs_total" not in body
    assert "local_bridge_reachable" not in body
    assert "waiting_handoffs" not in body
    assert "diagnostics_url" not in body


def test_auth_middleware_exempts_health(monkeypatch):
    monkeypatch.setenv("OCTOPUS_API_TOKEN", "secret-test-token")
    client = TestClient(app)

    # Health remains exempt
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_url_safety_utility():
    assert is_safe_http_url("https://example.com/api") is True
    assert is_safe_http_url("http://127.0.0.1:8000") is False
    assert is_safe_http_url("http://localhost:3000") is False
    assert is_safe_http_url("http://metadata.google.internal") is False
    assert is_safe_http_url("ftp://example.com") is False


def test_sqlite_store_smoke():
    with tempfile.TemporaryDirectory(prefix="kane-store-test-") as tmpdir:
        db_path = Path(tmpdir) / "smoke.db"
        store = SQLiteStore(db_path=db_path)
        try:
            assert store.list_conversations() == []
        finally:
            store.close()
