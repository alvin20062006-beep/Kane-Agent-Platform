from fastapi import APIRouter
from time import perf_counter

from ..settings_env import get_api_data_dir, get_persistence_backend
from ..version import PLATFORM_VERSION
from ..services.watchdog_metrics import build_metrics, build_watchdog_status, probe_local_bridge_detailed
from ..startup_timing import summary as startup_summary

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {
        "status": "ok",
        "service": "kane-agent-platform-api",
        "version": PLATFORM_VERSION,
        "persistence": get_persistence_backend(),
        "api_data_dir": str(get_api_data_dir()),
        "startup": startup_summary(),
        "diagnostics_url": "/health/diagnostics",
    }


@router.get("/health/diagnostics")
def health_diagnostics():
    started = perf_counter()
    phases = []

    def mark(name: str, phase_started: float) -> float:
        now = perf_counter()
        phases.append({"name": name, "ms": round((now - phase_started) * 1000, 2)})
        return now

    phase_started = perf_counter()
    bridge_probe = probe_local_bridge_detailed()
    phase_started = mark("probe_local_bridge", phase_started)
    metrics = build_metrics(bridge_probe=bridge_probe)
    phase_started = mark("build_metrics", phase_started)
    watchdog = build_watchdog_status(bridge_probe=bridge_probe)
    phase_started = mark("build_watchdog_status", phase_started)
    startup = startup_summary()
    phase_started = mark("startup_summary", phase_started)
    total_ms = round((perf_counter() - started) * 1000, 2)
    return {
        "status": "ok",
        "service": "kane-agent-platform-api",
        "version": PLATFORM_VERSION,
        "persistence": get_persistence_backend(),
        "api_data_dir": str(get_api_data_dir()),
        "tasks_total": metrics["tasks"]["total"],
        "runs_total": metrics["runs"]["total"],
        "local_bridge_reachable": metrics["local_bridge"]["reachable"],
        "waiting_handoffs": watchdog.summary.waiting_handoffs,
        "startup": startup,
        "profile": {"total_ms": total_ms, "phases": phases},
    }

