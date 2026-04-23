from fastapi import APIRouter

from ..settings_env import get_api_data_dir, get_persistence_backend
from ..services.watchdog_metrics import build_metrics, build_watchdog_status

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    metrics = build_metrics()
    watchdog = build_watchdog_status()
    return {
        "status": "ok",
        "service": "octopus-platform-api",
        "beta": True,
        "persistence": get_persistence_backend(),
        "api_data_dir": str(get_api_data_dir()),
        "tasks_total": metrics["tasks"]["total"],
        "runs_total": metrics["runs"]["total"],
        "local_bridge_reachable": metrics["local_bridge"]["reachable"],
        "waiting_handoffs": watchdog.summary.waiting_handoffs,
    }

