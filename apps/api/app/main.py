from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .bootstrap import bootstrap_if_empty
from .security.auth import ApiAuthMiddleware
from .routes.health import router as health_router
from .routes.integrations import router as integrations_router
from .routes.resources import router as resources_router
from .routes.streams import router as streams_router
from .routes.v2.platform import router as platform_router
from .services.runtime_supervision import start_runtime_supervision_thread
from .services.task_status_reconciliation import reconcile_all_tasks_with_latest_runs
from .services.worker_queue import start_worker_thread
from .settings_env import get_cors_allow_origins, get_runtime_supervision_enabled
from .startup_timing import mark
from .version import PLATFORM_VERSION


@asynccontextmanager
async def lifespan(app: FastAPI):
    mark("lifespan.begin")
    reconcile_all_tasks_with_latest_runs(source="api_startup")
    mark("task_reconciliation.done")
    start_worker_thread()
    mark("worker_thread.started")
    if get_runtime_supervision_enabled():
        start_runtime_supervision_thread()
        mark("supervision_thread.started")
    else:
        mark("supervision_thread.skipped")
    mark("lifespan.ready")
    yield


def create_app() -> FastAPI:
    mark("create_app.begin")
    app = FastAPI(
        title="Kane Agent Platform API",
        version=PLATFORM_VERSION,
        description="Kane Agent Platform control-plane API: tasks, runs, conversations, skills, optional Local Bridge. "
        "Default file persistence; optional Postgres. Not a hardened multi-tenant SaaS by default.",
        lifespan=lifespan,
    )
    mark("fastapi.init")

    app.add_middleware(ApiAuthMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_cors_allow_origins(),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(integrations_router)
    app.include_router(resources_router, prefix="/v1")
    app.include_router(streams_router)
    app.include_router(platform_router)
    mark("routers.registered")

    bootstrap_if_empty()
    mark("bootstrap.done")

    return app


mark("modules.imported")

app = create_app()
