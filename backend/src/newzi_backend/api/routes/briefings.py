"""Briefing deliveries, history, listening progress and audio."""
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse

from ...product_backend import not_found
from ..deps import accepted, call, current_user, json_body, service_of

router = APIRouter(prefix="/api/v1/me/briefings")


@router.get("/today")
async def today(request: Request, uid: str = Depends(current_user)):
    return await call(request, service_of(request).client_briefing, uid)


@router.post("/refresh")
async def refresh(request: Request, uid: str = Depends(current_user)):
    """Internal/admin compatibility: the mobile client relies on scheduled deliveries."""
    return accepted(await call(request, service_of(request).request_refresh, uid))


@router.post("/now")
async def on_demand(request: Request, uid: str = Depends(current_user)):
    """Premium "Gerar agora": poll /generations/{id} until READY, then open its delivery_id."""
    return accepted(await call(request, service_of(request).request_on_demand, uid))


@router.get("/search")
async def search(request: Request, uid: str = Depends(current_user), q: str = ""):
    """Premium: stories of past briefings matching every word of ``q``."""
    return await call(request, service_of(request).search_briefings, uid, q)


@router.get("/generations/{generation_id}")
async def generation(generation_id: str, request: Request, uid: str = Depends(current_user)):
    return await call(request, service_of(request).generation_status, uid, generation_id)


@router.post("/generations/{generation_id}/audio/retry")
async def retry_generation_audio(generation_id: str, request: Request, uid: str = Depends(current_user)):
    return accepted(await call(request, service_of(request).retry_generation_audio, uid, generation_id))


@router.get("")
async def history(request: Request, uid: str = Depends(current_user)):
    params = request.query_params
    return await call(request, service_of(request).history_page, uid, params.get("limit", 20), params.get("cursor", 0))


@router.put("/{delivery_id}/progress")
async def listening_progress(delivery_id: str, request: Request, uid: str = Depends(current_user)):
    return await call(request, service_of(request).listening_progress, uid, delivery_id, await json_body(request))


@router.get("/{delivery_id}/audio")
async def audio(delivery_id: str, request: Request, uid: str = Depends(current_user)):
    return await call(request, service_of(request).briefing_audio, uid, delivery_id)


@router.post("/{delivery_id}/audio/retry")
async def retry_audio(delivery_id: str, request: Request, uid: str = Depends(current_user)):
    return accepted(await call(request, service_of(request).retry_briefing_audio, uid, delivery_id))


@router.get("/{delivery_id}/audio/file")
async def audio_file(delivery_id: str, request: Request, uid: str = Depends(current_user),
                     voice: str | None = None, v: str | None = None):
    service = service_of(request)
    path, mime_type = await call(request, service.briefing_audio_file, uid, delivery_id, voice, v)
    path = Path(path).resolve()
    if service.audio.storage.root not in path.parents or not path.is_file():
        raise not_found("audio not available")
    # FileResponse answers Range requests, so players can seek and stream instead of downloading first.
    return FileResponse(path, media_type=mime_type, headers={"Cache-Control": "private, max-age=3600"})


@router.get("/{delivery_id}")
async def briefing(delivery_id: str, request: Request, uid: str = Depends(current_user)):
    return await call(request, service_of(request).briefing, uid, delivery_id)
