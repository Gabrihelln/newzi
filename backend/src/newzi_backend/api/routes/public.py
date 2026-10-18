"""Health, catalog and local-identity routes."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from ...product_backend import not_found
from ..deps import call, client_key, created, current_user, json_body, service_of

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    return {"status": "ok", "service": "newzi-product-backend", "database": service_of(request).config.database_dialect}


@router.get("/ready")
async def ready(request: Request):
    service = service_of(request)
    await call(request, lambda: service.repo.db.execute("SELECT 1").fetchone())
    return {"status": "ready", "database": "ok"}


@router.get("/health/worker")
async def worker_health(request: Request):
    """Every worker role ran within WORKER_STALE_SECONDS (200) or some did not (503), plus queue backlog."""
    from ...scheduling import worker_health as collect
    service = service_of(request)
    report = await call(request, lambda: collect(service.repo))
    return JSONResponse(report, status_code=200 if report["status"] == "ok" else 503)


@router.get("/api/v1/topics")
async def topics(request: Request):
    service = service_of(request)
    return {"items": await call(request, service.repo.list_topics)}


@router.get("/api/v1/client/config")
async def client_config(request: Request):
    return await call(request, service_of(request).client_config)


@router.post("/api/v1/auth/register")
async def register(request: Request):
    return created(await call(request, service_of(request).register, await json_body(request), client_key(request)))


@router.post("/api/v1/auth/login")
async def login(request: Request):
    return await call(request, service_of(request).login, await json_body(request), client_key(request))


@router.post("/api/v1/auth/logout")
async def logout(request: Request, uid: str = Depends(current_user)):
    service = service_of(request)
    body = await json_body(request)
    return await call(request, service.logout, uid, service.bearer_token(request.headers.get("authorization")), body.get("push_token"))


@router.get("/api/v1/avatars/{name}")
async def avatar(name: str):
    """Profile photos: public like any profile picture, behind a random file name."""
    from ...avatars import avatar_path
    path = avatar_path(name)
    if not path:
        raise not_found("avatar not found")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"})


@router.get("/api/v1/articles/{article_id}/image")
async def article_image(article_id: str, request: Request, uid: str = Depends(current_user)):
    image = await call(request, service_of(request).article_image, article_id)
    return Response(image, media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})
