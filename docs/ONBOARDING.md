# Onboarding

New users begin with `onboarding_status = NOT_STARTED`. `GET /api/v1/me/onboarding` returns the state and current preference object. `PUT /api/v1/me/onboarding` validates and persists the complete preference contract; a successful request sets `COMPLETED`.

The backend accepts only catalog topics (`ARTIFICIAL_INTELLIGENCE`, `TECHNOLOGY`, `BUSINESS`), languages `pt-BR`/`en`, country scopes `LOCAL`/`GLOBAL`/`BOTH`, IANA timezones, local `HH:MM` delivery times and briefing sizes 5/10/15. Profile-affecting changes are consumed by the existing scheduler/profile-key path; historical briefings are not rewritten.
