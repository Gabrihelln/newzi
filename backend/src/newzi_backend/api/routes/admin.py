"""Analytics Newzi (painel.newzi.app): sign-in, the numbers of each panel screen, and its two kinds of change:
Premium given from the panel (admin_premium.py) and announcements or promotions by push (admin_push.py).

The panel signs in with its own e-mail and password (``admin.py``) and keeps the session in an HttpOnly cookie. Every
route answers 404 while the panel is not configured, or when ADMIN_HOST is set and the request came to another host.
Changes also need the ``X-Newzi-Panel`` header, which a page on another site cannot send, and each one is written
to ``admin_actions``.
"""
import asyncio

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ... import admin, admin_metrics, admin_premium, admin_push
from ...product_backend import ApiError, not_found
from ..deps import call, client_key, json_body, service_of

router = APIRouter(prefix="/api/v1/admin")
COOKIE = "newzi_admin"
WRITE_HEADER = "x-newzi-panel"


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


# ------------------------------------------------------------- changes
async def admin_write(request: Request):
    """Dependency for changes: a panel session plus the panel's own header."""
    await admin_session(request)
    if request.headers.get(WRITE_HEADER) != "1":
        raise ApiError("FORBIDDEN", "missing panel header", 403)


async def _change(request, action, function, *args, detail=None):
    """Run a change, turning LookupError into 409, and log it in admin_actions."""
    repo = service_of(request).repo
    try:
        result = await call(request, function, repo, *args)
    except LookupError as exc:
        raise ApiError("CONFLICT", str(exc), 409) from None
    await call(request, admin.record, repo, action, actor=admin.admin_email(), client=client_key(request), detail=detail or {})
    return result


def _confirmed(body):
    if str(body.get("confirm") or "").strip().upper() != "ENVIAR":
        raise ApiError("CONFIRMATION_REQUIRED", 'type ENVIAR to confirm', 400)


@router.get("/premium-grants", dependencies=[Depends(admin_session)])
async def premium_grants(request: Request):
    return await call(request, admin_premium.grants, service_of(request).repo)


@router.post("/premium-grants", dependencies=[Depends(admin_write)])
async def give_premium(request: Request):
    body = await json_body(request)
    actor = admin.admin_email()
    result = await _change(request, "premium_give", lambda repo: admin_premium.give(repo, body, actor),
                           detail={key: body.get(key) for key in ("emails", "start_day", "end_day", "reason", "note")})
    return result


@router.put("/premium-grants/{grant_id}", dependencies=[Depends(admin_write)])
async def change_premium(grant_id: str, request: Request):
    body = await json_body(request)
    return await _change(request, "premium_change", admin_premium.change, grant_id, body,
                         detail={"grant_id": grant_id, **{key: body.get(key) for key in ("start_day", "end_day", "reason", "note")}})


@router.post("/premium-grants/{grant_id}/revoke", dependencies=[Depends(admin_write)])
async def revoke_premium(grant_id: str, request: Request):
    actor = admin.admin_email()
    return await _change(request, "premium_revoke", lambda repo: admin_premium.end(repo, grant_id, actor), detail={"grant_id": grant_id})


@router.get("/push", dependencies=[Depends(admin_session)])
async def push_campaigns(request: Request):
    return await call(request, admin_push.campaigns, service_of(request).repo)


@router.post("/push/preview", dependencies=[Depends(admin_write)])
async def push_preview(request: Request):
    body = await json_body(request)
    return await call(request, admin_push.preview, service_of(request).repo, body)


def _push_detail(body):
    return {key: body.get(key) for key in ("kind", "title", "body", "target", "audience", "scheduled_for")}


@router.post("/push", dependencies=[Depends(admin_write)])
async def create_push(request: Request):
    body = await json_body(request)
    _confirmed(body)
    return await _change(request, "push_create", admin_push.create, body, detail=_push_detail(body))


@router.put("/push/{campaign_id}", dependencies=[Depends(admin_write)])
async def update_push(campaign_id: str, request: Request):
    body = await json_body(request)
    _confirmed(body)
    return await _change(request, "push_update", admin_push.update, campaign_id, body, detail={"id": campaign_id, **_push_detail(body)})


@router.post("/push/{campaign_id}/cancel", dependencies=[Depends(admin_write)])
async def cancel_push(campaign_id: str, request: Request):
    return await _change(request, "push_cancel", admin_push.cancel, campaign_id, detail={"id": campaign_id})


@router.post("/push/{campaign_id}/send", dependencies=[Depends(admin_write)])
async def send_push(campaign_id: str, request: Request):
    _confirmed(await json_body(request))
    return await _change(request, "push_send_now", admin_push.send_now, campaign_id, detail={"id": campaign_id})


@router.get("/actions", dependencies=[Depends(admin_session)])
async def actions(request: Request):
    """What was changed from the panel, newest first."""
    repo = service_of(request).repo
    return await call(request, lambda: [dict(row) for row in repo.db.execute(
        "SELECT action,client,detail_json,ok,created_at FROM admin_actions WHERE action<>'login' ORDER BY id DESC LIMIT 200").fetchall()])
