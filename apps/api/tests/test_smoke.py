from concurrent.futures import ThreadPoolExecutor
import threading
import time

from fastapi.testclient import TestClient

from app.main import app
from app.services import watchdog_metrics


class _FakeBridgeResponse:
    def __init__(self, body: dict):
        self.status_code = 200
        self._body = body

    def json(self):
        return self._body


def test_app_imports_and_health_responds():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "kane-agent-platform-api"
    assert body["diagnostics_url"] == "/health/diagnostics"
    assert "tasks_total" not in body
    assert "runs_total" not in body
    assert "local_bridge_reachable" not in body
    assert "waiting_handoffs" not in body
    assert "profile" not in body


def test_health_diagnostics_keeps_heavy_status_fields():
    client = TestClient(app)

    response = client.get("/health/diagnostics")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "kane-agent-platform-api"
    assert "tasks_total" in body
    assert "runs_total" in body
    assert "local_bridge_reachable" in body
    assert "waiting_handoffs" in body
    assert body["profile"]["total_ms"] >= 0


def test_local_bridge_probe_cache_and_fresh_semantics(monkeypatch):
    calls: list[str] = []

    class FakeClient:
        def __init__(self, timeout: float):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url: str):
            calls.append(url)
            if url.endswith("/health"):
                return _FakeBridgeResponse({"bridge_version": "test-bridge", "supported_adapters": []})
            return _FakeBridgeResponse({"last_execute": {"at": "mocked"}})

    monkeypatch.setattr(watchdog_metrics.httpx, "Client", FakeClient)
    watchdog_metrics.clear_bridge_probe_cache()
    try:
        first = watchdog_metrics.probe_local_bridge_detailed(fresh=True)
        second = watchdog_metrics.probe_local_bridge_detailed()
        third = watchdog_metrics.probe_local_bridge_detailed(fresh=True)
    finally:
        watchdog_metrics.clear_bridge_probe_cache()

    assert first["probe_cache"]["hit"] is False
    assert second["probe_cache"]["hit"] is True
    assert third["probe_cache"]["hit"] is False
    assert len(calls) == 4
    assert calls[0].endswith("/health")
    assert calls[1].endswith("/v1/status")


def test_local_bridge_probe_singleflight_coalesces_read_only_misses(monkeypatch):
    calls = 0
    lock = threading.Lock()

    def fake_uncached(url: str):
        nonlocal calls
        with lock:
            calls += 1
        time.sleep(0.05)
        return {
            "url": url,
            "reachable": True,
            "error": None,
            "health": {"bridge_version": "test-bridge"},
            "bridge_status": {"agents_registered": 0},
            "hints": [],
            "probed_at": "2026-07-07T00:00:00+00:00",
            "probe_elapsed_ms": 50.0,
        }

    monkeypatch.setattr(watchdog_metrics, "get_local_bridge_url", lambda: "http://bridge.test")
    monkeypatch.setattr(watchdog_metrics, "_probe_local_bridge_detailed_uncached", fake_uncached)
    watchdog_metrics.clear_bridge_probe_cache()
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: watchdog_metrics.probe_local_bridge_detailed(), range(8)))
    finally:
        watchdog_metrics.clear_bridge_probe_cache()

    assert calls == 1
    assert all(item["reachable"] is True for item in results)
    assert sum(1 for item in results if item["probe_cache"]["hit"] is False) == 1
    assert sum(1 for item in results if item["probe_cache"]["hit"] is True) == 7


def test_status_endpoint_responds():
    client = TestClient(app)

    response = client.get("/api/adapters/status")

    assert response.status_code == 200
    body = response.json()
    assert body["_schema"] == "adapters_status_v1"
    assert "local_bridge" in body


def test_codex_cli_default_capabilities_are_code_agent():
    client = TestClient(app)

    response = client.post(
        "/agents",
        json={
            "agent_id": "qa_codex_defaults",
            "display_name": "QA Codex Defaults",
            "type": "external",
            "adapter_id": "codex_cli",
            "integration_mode": "external",
            "integration_channels": ["cli"],
            "control_depth": "assisted",
        },
    )

    assert response.status_code == 200
    caps = response.json()["data"]["capabilities"]
    assert caps["can_code"] is True
    assert caps["can_run_local_commands"] is True
    assert caps["supports_structured_task"] is True
    assert caps["supports_handoff"] is True
    assert caps["supports_callback"] is True


def _collect_route_paths(routes, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    for route in routes:
        path = getattr(route, "path", None)
        if path:
            paths.add(f"{prefix}{path}")

        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            include_context = getattr(route, "include_context", None)
            include_prefix = getattr(include_context, "prefix", "") if include_context else ""
            paths.update(_collect_route_paths(original_router.routes, f"{prefix}{include_prefix}"))

        nested_routes = getattr(route, "routes", None)
        if nested_routes:
            paths.update(_collect_route_paths(nested_routes, prefix))
    return paths


def test_core_routes_are_registered():
    paths = _collect_route_paths(app.routes)

    assert "/health" in paths
    assert "/health/diagnostics" in paths
    assert "/api/system/capabilities" in paths
    assert "/api/adapters/status" in paths
    assert "/tasks" in paths
    assert "/skills" in paths
    assert "/memory" in paths
