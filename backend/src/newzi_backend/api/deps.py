"""Request helpers shared by the routers."""
import json
import logging
import os

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from ..product_backend import ApiError

log = logging.getLogger("news_engine.product")
_LOOPBACK = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}


def service_of(request):
    return request.app.state.service


async def call(request, function, *args, **kwargs):
    """Run blocking service code in the thread pool and end that thread's transaction afterwards."""
    service = service_of(request)

    def run():
        try:
            return function(*args, **kwargs)
        finally:
            # Pool threads keep their connection for reuse; never leave a transaction open on it.
            service.repo.release_thread_connection()
    return await run_in_threadpool(run)


async def json_body(request):
    raw = await request.body()
    if not raw:
        return {}
    try:
        body = json.loads(raw)
    except ValueError:
        raise ApiError("INVALID_JSON", "request body is not valid JSON", 400) from None
    if not isinstance(body, dict):
        raise ApiError("INVALID_JSON", "request body must be a JSON object", 400)
    return body


def client_key(request):
    peer = request.client.host if request.client else ""
    # Only a local reverse proxy (deploy/nginx sets X-Real-IP) may name the real client;
    # a direct client cannot spoof its address through the header.
    if peer in _LOOPBACK:
        forwarded = (request.headers.get("x-real-ip") or "").strip()
        if forwarded:
            return forwarded
    return peer or "unknown"


async def current_user(request: Request):
    """Dependency: the authenticated user's id, or a 401 in the API envelope."""
    identity, reason = await call(request, service_of(request).authenticate, request.headers.get("authorization"))
    if not identity:
        log.warning("[Backend Auth] authorization_rejected reason=%s", reason or "AUTH_REQUIRED")
        raise ApiError("AUTH_REQUIRED", "authentication required", 401)
    return identity.user_id


def dev_routes_enabled(service):
    # The environment snapshot is taken at startup; the runtime check also keeps tests/embedders
    # that change the environment after construction from exposing development routes.
    runtime_env = str(os.getenv("APP_ENV", service.config.app_env)).strip().lower()
    runtime_flag = str(os.getenv("ENABLE_DEV_ENDPOINTS") or "true").lower()
    return service.config.dev_endpoints_enabled and runtime_env != "production" and runtime_flag not in {"0", "false", "no", "off"}


def created(payload): return JSONResponse(payload, status_code=201)
def accepted(payload): return JSONResponse(payload, status_code=202)
