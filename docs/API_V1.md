# NEWS ENGINE Product API v1

Run from the repository root with `python backend/product_api.py` after configuring root `.env` as described in `README.md`.

Endpoints:

- `GET /health`
- `GET /api/v1/topics`
- `GET /api/v1/users/{user_id}`
- `GET /api/v1/users/{user_id}/preferences`
- `PUT /api/v1/users/{user_id}/preferences`
- `GET /api/v1/users/{user_id}/briefings/today`
- `GET /api/v1/users/{user_id}/briefings`
- `GET /api/v1/users/{user_id}/briefings/{briefing_id}`
- `POST /api/v1/dev/users/{user_id}/briefings/generate` (development only)
- `GET /api/v1/dev/jobs` (development only)
- `POST /api/v1/dev/scheduler/run` (development only)
- `POST /api/v1/dev/worker/run` (development only)

The briefing response exposes the stable product fields `id`, `date`, `status`, `generated_at`, `items`; each item exposes position, editorial fields, confidence, evidence quality, trace ID, warnings and source references. Internal engine payloads and prompts are not returned.

Preferences validate IANA timezones, `HH:MM` local briefing times, supported topics, country scope and briefing sizes 5/10/15.

Operational DEV endpoints are disabled when `APP_ENV=production` or `ENABLE_DEV_ENDPOINTS=false`.

Authenticated client routes, session behavior and onboarding are documented in [CLIENT_API.md](CLIENT_API.md), [AUTH_ARCHITECTURE.md](AUTH_ARCHITECTURE.md) and [ONBOARDING.md](ONBOARDING.md).
