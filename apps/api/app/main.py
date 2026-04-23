from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .bootstrap import bootstrap_if_empty
from .routes.health import router as health_router
from .routes.integrations import router as integrations_router
from .routes.resources import router as resources_router
from .routes.streams import router as streams_router
from .routes.v2.platform import router as platform_router
from .services.worker_queue import start_worker_thread


def create_app() -> FastAPI:
    app = FastAPI(
        title="Octopus Platform API",
        version="0.2.0-beta",
        description="Public Free Beta API: real task lifecycle + file persistence. Not production-hardened.",
    )

    # Beta: allow any origin for VPS demos; do not rely on credentialed cross-origin cookies.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(integrations_router)
    app.include_router(resources_router, prefix="/v1")
    app.include_router(streams_router)
    app.include_router(platform_router)

    bootstrap_if_empty()

    # Ensure worker is started even in TestClient environments where startup hooks can be finicky.
    start_worker_thread()

    @app.on_event("startup")
    def _start_worker() -> None:
        # Beta worker: in-process background thread processing queued runs (status=pending).
        start_worker_thread()

    return app


app = create_app()
