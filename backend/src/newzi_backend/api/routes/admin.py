"""Analytics Newzi (painel.newzi.app): sign-in and the read-only numbers of each panel screen.

The panel signs in with its own e-mail and password (``admin.py``) and keeps the session in an HttpOnly cookie. Every
route answers 404 while the panel is not configured, or when ADMIN_HOST is set and the request came to another host.
"""
import asyncio

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ... import admin, admin_metrics
from ...product_backend import ApiError, not_found
from ..deps import call, client_key, json_body, service_of

router = APIRouter(prefix="/api/v1/admin")
COOKIE = "newzi_admin"


def _available(request):
    if not admin.configured() or not admin.allowed_host(request.headers.get("host")):
        raise not_found()


async def admin_session(request: Request):
    """Dependency: a valid panel session, or a 401 in the API envelope."""
    _available(request)
    if not await call(request, admin.session_valid, service_of(request).repo, request.cookies.get(COOKIE)):
        raise ApiError("AUTH_REQUIRED", "authentication required", 401)


@router.post("/login")
async def login(request: Request):
    _available(request)
    body = await json_body(request)
    repo = service_of(request).repo
    try:
        token = await call(request, admin.login, repo, body.get("email"), body.get("password"), client_key(request))
    except LookupError as locked:
        raise ApiError("LOCKED", f"too many wrong passwords; try again after {locked.args[0]:%H:%M} UTC", 429) from None
    except PermissionError:
        await asyncio.sleep(1)       # slows down guessing; five misses in a row also lock the sign-in
        raise ApiError("INVALID_CREDENTIALS", "invalid credentials", 401) from None
    response = JSONResponse({"ok": True, "email": admin.admin_email()})
    response.set_cookie(COOKIE, token, max_age=admin.SESSION_HOURS * 3600, httponly=True, secure=True, samesite="strict",
                        path="/api/v1/admin")
    return response


@router.post("/logout")
async def logout(request: Request):
    _available(request)
    await call(request, admin.logout, service_of(request).repo, request.cookies.get(COOKIE))
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE, path="/api/v1/admin")
    return response


@router.get("/session", dependencies=[Depends(admin_session)])
async def session():
    return {"ok": True, "email": admin.admin_email()}


def _screen(path, function, *params):
    """A GET route for one panel screen, passing the listed query parameters through."""
    async def route(request: Request):
        repo = service_of(request).repo
        kwargs = {name: request.query_params[name] for name in params if request.query_params.get(name) not in (None, "")}
        return await call(request, function, repo, **kwargs)
    router.add_api_route(path, route, methods=["GET"], dependencies=[Depends(admin_session)], name="admin_" + function.__name__)


_screen("/overview", admin_metrics.overview, "days")
_screen("/users", admin_metrics.users, "query", "plan", "page")
_screen("/retention", admin_metrics.retention, "weeks")
_screen("/briefings", admin_metrics.briefings, "days")
_screen("/content", admin_metrics.content, "days")
_screen("/notifications", admin_metrics.notifications, "days")
_screen("/subscriptions", admin_metrics.subscriptions, "days")
_screen("/football", admin_metrics.football, "days")
_screen("/system", admin_metrics.system)


@router.get("/users/{user_id}", dependencies=[Depends(admin_session)])
async def user_detail(user_id: str, request: Request):
    detail = await call(request, admin_metrics.user_detail, service_of(request).repo, user_id)
    if not detail:
        raise not_found("user not found")
    return detail
