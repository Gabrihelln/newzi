"""FastAPI application for the product API.

Routes are thin: they parse the request, call a ``ProductService`` method in the worker
thread pool and render the result. Errors keep the API's envelope:
``{"error": {"code", "message", "request_id"}}``.
"""
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..product_backend import ApiError, ProductService
from ..subscriptions import PremiumRequired
from .routes import admin, briefings, dev, me, public

log = logging.getLogger("news_engine.product")
MAX_BODY_BYTES = 1024 * 1024


def error_response(code, message, status, request=None, **extra):
    request_id = getattr(getattr(request, "state", None), "request_id", None) or "req_" + uuid.uuid4().hex
    return JSONResponse({"error": {"code": code, "message": message, "request_id": request_id, **extra}}, status_code=status)


def create_app(service=None):
    app = FastAPI(title="Newzi Product API", version="1", docs_url=None, redoc_url=None, openapi_url="/api/v1/openapi.json")
    app.state.service = service or ProductService()
    origins = app.state.service.config.cors_origins
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(origins), allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = "req_" + uuid.uuid4().hex
        length = request.headers.get("content-length")
        if length:
            try: oversized = int(length) > MAX_BODY_BYTES or int(length) < 0
            except ValueError: return error_response("VALIDATION_ERROR", "invalid Content-Length", 400, request)
            if oversized: return error_response("PAYLOAD_TOO_LARGE", "request body too large", 413, request)
        try:
            return await call_next(request)
        except Exception as exc:
            # Always recorded: the client only receives the request_id, so this log line is the
            # sole trace of a production failure. The query string is omitted (it may carry user input).
            log.error("product api request failed request_id=%s method=%s path=%s", request.state.request_id,
                      request.method, request.url.path, exc_info=exc)
            return error_response("INTERNAL_ERROR", "internal error", 500, request)

    @app.exception_handler(ApiError)
    async def api_error(request, exc):
        return error_response(exc.code, exc.message, exc.status, request)

    @app.exception_handler(PremiumRequired)
    async def premium_required(request, exc):
        # The app opens the Premium sheet of ``feature``.
        return error_response("PREMIUM_REQUIRED", str(exc), 403, request, feature=exc.feature)

    @app.exception_handler(ValueError)
    async def validation_error(request, exc):
        return error_response("VALIDATION_ERROR", str(exc), 400, request)

    @app.exception_handler(PermissionError)
    async def permission_error(request, exc):
        return error_response("FORBIDDEN", "resource access denied", 403, request)

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(request, exc):
        return error_response("VALIDATION_ERROR", "invalid request parameters", 400, request)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        if exc.status_code == 405:
            return error_response("METHOD_NOT_ALLOWED", "method not allowed", 405, request)
        if exc.status_code == 404:
            return error_response("RESOURCE_NOT_FOUND", "not found", 404, request)
        return error_response("HTTP_ERROR", str(exc.detail), exc.status_code, request)

    for module in (public, me, briefings, dev, admin):
        app.include_router(module.router)
    return app
