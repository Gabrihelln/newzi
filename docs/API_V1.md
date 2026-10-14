# NEWS ENGINE Product API v1

Run from the repository root with `python backend/product_api.py` (FastAPI on uvicorn) after configuring root `.env` as described in `README.md`. The OpenAPI description is served at `/api/v1/openapi.json`; client routes are listed in `CLIENT_API.md`.

The former `/api/v1/users/{user_id}/...` compatibility routes and the legacy per-user briefing generator were removed; clients use `/api/v1/me/...`.

Endpoints outside `/api/v1/me`:

- `GET /health`, `GET /ready`
- `GET /health/worker`: 200 when every worker role completed a cycle within `WORKER_STALE_SECONDS`, 503 otherwise; reports missing roles, per-process cycle age and queue backlog, without ids, hosts or error text
- `GET /api/v1/topics`, `GET /api/v1/client/config`
- `GET /api/v1/dev/jobs` (development only)
- `GET /api/v1/dev/sources/health` (development only): per-source status (`BROKEN`, `FAILING`, `DEGRADED`, `SILENT`, `OK`, `DISABLED`), an actionable `diagnosis` (`FEED_URL_NOT_FOUND`, `ACCESS_BLOCKED`, `FEED_ABANDONED`, ...) and indexed volume over 24 h / 7 days. Also `python engine/main.py --source-health`.
- `POST /api/v1/dev/scheduler/run` (development only)
- `POST /api/v1/dev/worker/run` (development only)

The briefing response exposes the stable product fields `id`, `date`, `status`, `generated_at`, `items`; each item exposes position, editorial fields, confidence, evidence quality, trace ID, warnings and source references. Internal engine payloads and prompts are not returned.

Preferences validate IANA timezones, `HH:MM` local briefing times, supported topics, country scope and briefing sizes 5/10/15.

Operational DEV endpoints are disabled when `APP_ENV=production` or `ENABLE_DEV_ENDPOINTS=false`.

Authenticated client routes, session behavior and onboarding are documented in [CLIENT_API.md](CLIENT_API.md), [AUTH_ARCHITECTURE.md](AUTH_ARCHITECTURE.md) and [ONBOARDING.md](ONBOARDING.md).
