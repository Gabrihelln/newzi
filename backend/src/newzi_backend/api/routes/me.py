"""The signed-in user's profile, preferences, devices, news and saved items."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, Response

from ...product_backend import not_found
from ..deps import call, created, current_user, json_body, service_of

router = APIRouter(prefix="/api/v1/me")


@router.get("")
async def me(request: Request, uid: str = Depends(current_user)):
    repo = service_of(request).repo
    return await call(request, lambda: repo.public_user(repo.get_user(uid)))


@router.delete("")
async def delete_account(request: Request, uid: str = Depends(current_user)):
    await call(request, service_of(request).delete_account, uid)
    return Response(status_code=204)


@router.post("/avatar")
async def upload_avatar(request: Request, uid: str = Depends(current_user)):
    """Editar perfil › Trocar foto: a base64 image, stored resized; returns its public URL path."""
    return await call(request, service_of(request).upload_avatar, uid, await json_body(request))


@router.get("/preferences")
async def preferences(request: Request, uid: str = Depends(current_user)):
    return await call(request, service_of(request).preferences, uid)


@router.put("/preferences")
async def save_preferences(request: Request, uid: str = Depends(current_user)):
    return await call(request, service_of(request).save_preferences, uid, await json_body(request))


@router.get("/onboarding")
async def onboarding(request: Request, uid: str = Depends(current_user)):
    return await call(request, service_of(request).onboarding, uid)


@router.put("/onboarding")
async def complete_onboarding(request: Request, uid: str = Depends(current_user)):
    return await call(request, service_of(request).complete_onboarding, uid, await json_body(request))


@router.get("/audio/voices")
async def voices(request: Request, uid: str = Depends(current_user), language: str | None = None):
    return await call(request, service_of(request).voice_catalog, uid, language)


@router.get("/audio/voices/{voice_id}/preview")
async def voice_preview(voice_id: str, request: Request, uid: str = Depends(current_user), language: str | None = None):
    path, mime_type = await call(request, service_of(request).voice_preview, uid, voice_id, language)
    return FileResponse(path, media_type=mime_type, headers={"Cache-Control": "private, max-age=3600"})


@router.post("/devices")
async def register_device(request: Request, uid: str = Depends(current_user)):
    return created(await call(request, service_of(request).register_device, uid, await json_body(request)))


@router.delete("/devices/{device_id}")
async def disable_device(device_id: str, request: Request, uid: str = Depends(current_user)):
    if not await call(request, service_of(request).notifications.disable_device, uid, device_id):
        raise not_found("device not found")
    return Response(status_code=204)


@router.get("/notification-settings")
async def notification_settings(request: Request, uid: str = Depends(current_user)):
    return await call(request, service_of(request).notification_settings, uid)


@router.put("/notification-settings")
async def save_notification_settings(request: Request, uid: str = Depends(current_user)):
    return await call(request, service_of(request).notification_settings, uid, await json_body(request))


@router.get("/content/revision")
async def content_revision(request: Request, uid: str = Depends(current_user)):
    from ...content import get_content_revision
    return await call(request, get_content_revision, service_of(request).repo)


@router.get("/news")
async def news(request: Request, uid: str = Depends(current_user), q: str = "", topic: str | None = None,
               limit: str = "20", discovery: str = ""):
    items = await call(request, service_of(request).repo.latest_news, uid, limit, topic, q.strip(),
                       discovery.lower() in {"1", "true", "yes"})
    return {"items": items}


@router.get("/news/{story_id}")
async def story(story_id: str, request: Request, uid: str = Depends(current_user)):
    item = await call(request, service_of(request).repo.story, uid, story_id)
    if not item:
        raise not_found("story not found")
    return {"item": item}


@router.get("/articles/{story_id}/feedback")
async def article_feedback(story_id: str, request: Request, uid: str = Depends(current_user)):
    return await call(request, service_of(request).article_feedback, uid, story_id)


@router.put("/articles/{story_id}/feedback")
async def rate_article(story_id: str, request: Request, uid: str = Depends(current_user)):
    body = await json_body(request)
    return await call(request, service_of(request).article_feedback, uid, story_id, body.get("rating"), True)


@router.get("/football")
async def football(request: Request, uid: str = Depends(current_user), scope: str = ""):
    """Live and upcoming games worldwide; ``scope=explore`` is the Explore card, shown to everyone."""
    from ...football import football_for
    service = service_of(request)
    return await call(request, lambda: football_for(service.repo.get_preferences(uid), require_follow=scope != "explore"))


@router.get("/football/standings/{code}")
async def football_standings(request: Request, code: str, uid: str = Depends(current_user)):
    """One competition's table (BSA, CLI, PL...)."""
    from ...football import football_standings as standings
    return await call(request, lambda: standings(code))


@router.get("/trending")
async def trending(request: Request, uid: str = Depends(current_user)):
    return {"items": await call(request, service_of(request).trending, uid)}


@router.get("/home")
async def home(request: Request, uid: str = Depends(current_user)):
    return await call(request, service_of(request).client_home, uid)


@router.get("/saved/overview")
async def saved_overview(request: Request, uid: str = Depends(current_user)):
    return await call(request, service_of(request).repo.saved_overview, uid)


@router.put("/saved/{story_id}/progress")
async def saved_progress(story_id: str, request: Request, uid: str = Depends(current_user)):
    body = await json_body(request)
    return await call(request, service_of(request).saved_progress, uid, story_id, body.get("progress"))


@router.get("/saved")
async def saved(request: Request, uid: str = Depends(current_user)):
    params = request.query_params; service = service_of(request)
    if any(key in params for key in ("limit", "cursor", "topic")):
        return await call(request, service.saved_page, uid, params.get("limit", 40), params.get("cursor", 0), params.get("topic"))
    return {"items": await call(request, service.repo.saved_stories, uid)}


@router.put("/saved")
async def save_story(request: Request, uid: str = Depends(current_user)):
    return await call(request, service_of(request).save_story, uid, await json_body(request))


@router.delete("/saved/{story_id}")
async def remove_saved_story(story_id: str, request: Request, uid: str = Depends(current_user)):
    if not await call(request, service_of(request).repo.remove_saved_story, uid, story_id):
        raise not_found("saved story not found")
    return {"status": "ok"}


@router.get("/saved-briefings")
async def saved_briefings(request: Request, uid: str = Depends(current_user)):
    return {"items": await call(request, service_of(request).repo.saved_briefings, uid)}


@router.put("/saved-briefings")
async def save_briefing(request: Request, uid: str = Depends(current_user)):
    body = await json_body(request)
    return await call(request, service_of(request).save_briefing, uid, body.get("briefing_id"))


@router.delete("/saved-briefings/{briefing_id}")
async def remove_saved_briefing(briefing_id: str, request: Request, uid: str = Depends(current_user)):
    if not await call(request, service_of(request).repo.remove_saved_briefing, uid, briefing_id):
        raise not_found("saved briefing not found")
    return {"status": "ok"}


@router.get("/subscription")
async def subscription(request: Request, uid: str = Depends(current_user)):
    """The user's plan (Básico or Premium), its limits and the plans on offer."""
    from ...subscriptions import subscription_for
    service = service_of(request)
    return await call(request, lambda: subscription_for(service.repo, uid))
