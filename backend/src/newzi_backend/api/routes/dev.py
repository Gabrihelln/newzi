"""Development-only operations; every route answers 404 unless development routes are enabled."""
from fastapi import APIRouter, Request

from ...product_backend import not_found
from ..deps import accepted, call, dev_routes_enabled, service_of

router = APIRouter(prefix="/api/v1/dev")


def _service(request):
    service = service_of(request)
    if not dev_routes_enabled(service):
        raise not_found()
    return service


@router.get("/jobs")
async def jobs(request: Request):
    return await call(request, _service(request).dev_jobs)


@router.get("/users/{user_id}/briefing/diagnostic")
async def briefing_diagnostic(user_id: str, request: Request):
    service = _service(request)
    identity, _ = await call(request, service.authenticate, request.headers.get("authorization"))
    if not identity or identity.user_id != user_id:
        raise not_found()
    return await call(request, service.briefing_diagnostic, user_id)


@router.get("/sources/health")
async def sources_health(request: Request):
    from ...source_health import source_health_report
    return await call(request, source_health_report, _service(request).repo)


@router.api_route("/scheduler/run", methods=["GET", "POST"])
async def scheduler_run(request: Request):
    return await call(request, _service(request).scheduler.run_once)


@router.api_route("/worker/run", methods=["GET", "POST"])
async def worker_run(request: Request):
    return await call(request, _service(request).worker.run_once)


@router.post("/audio/run")
async def audio_run(request: Request):
    return await call(request, _service(request).audio.generate_pending)


@router.get("/audio/metrics")
async def audio_metrics(request: Request):
    return await call(request, _service(request).audio.metrics)


@router.post("/notifications/enqueue")
async def notifications_enqueue(request: Request):
    return await call(request, _service(request).notifications.enqueue_ready)


@router.post("/notifications/run")
async def notifications_run(request: Request):
    return await call(request, _service(request).notifications.run_once)


@router.post("/briefings/{identifier}/audio/generate")
async def generate_audio(identifier: str, request: Request):
    return accepted(await call(request, _service(request).dev_generate_audio, identifier))
