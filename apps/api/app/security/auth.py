"""Optional API token gate — off by default for local dev/tests."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..settings_env import get_api_token

_EXEMPT_PREFIXES = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
)


def _path_exempt(path: str) -> bool:
    return any(path == p or path.startswith(f"{p}/") for p in _EXEMPT_PREFIXES)


def _extract_token(request: Request) -> str | None:
    header = request.headers.get("X-Api-Key") or request.headers.get("x-api-key")
    if header and header.strip():
        return header.strip()
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def request_authorized(request: Request) -> bool:
    expected = get_api_token()
    if not expected:
        return True
    if _path_exempt(request.url.path):
        return True
    provided = _extract_token(request)
    return provided == expected


class ApiAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not request_authorized(request):
            return JSONResponse(status_code=401, content={"detail": "api_auth_required"})
        return await call_next(request)
