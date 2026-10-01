# Client API

Client-centric authenticated endpoints:

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/me`
- `GET|PUT /api/v1/me/preferences`
- `GET|PUT /api/v1/me/onboarding`
- `GET /api/v1/me/briefings/today`
- `GET /api/v1/me/briefings?limit=20&cursor=0`
- `GET /api/v1/me/briefings/{briefing_id}`
- `GET /api/v1/client/config`

Use `Authorization: Bearer <session-token>`. Error responses use `{error:{code,message,request_id}}`; they never expose stack traces. `today` returns `PENDING` when no delivery exists and never invokes the LLM. Briefing items expose only client fields and sources, not prompts, raw model output, fingerprints or internal scores.

Legacy `/api/v1/users/{user_id}/...` routes remain temporarily for compatibility. Operational `/api/v1/dev/...` routes are development-only and are disabled with `APP_ENV=production` or `ENABLE_DEV_ENDPOINTS=false`.
