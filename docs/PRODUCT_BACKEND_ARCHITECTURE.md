# NEWS ENGINE — Product Backend Architecture

> Nota histórica: o fluxo principal atual usa índice de conteúdo e edições compartilhadas por perfil. Consulte o `README.md` da raiz e `backend/src/newzi_backend/content.py` antes de seguir as seções de orquestração legada abaixo.

## Boundary

The engine remains responsible for collection, deterministic filtering, clustering, ranking, evidence acquisition and semantic summarization. The product backend owns users, preferences, local dates, persisted briefings, sources, API contracts and generation orchestration.

The adapter in `backend/src/newzi_backend/product_backend.py` consumes the structured Engine briefing fixture/output through the centralized path resolvers; it does not parse Markdown and does not reimplement editorial rules.

## Persistence

Development uses `backend/data/product_backend.sqlite3`, physically separate from `engine/data/news_engine.sqlite3`, LLM caches and observability databases. Schema creation is versioned through `schema_migrations` and creates tables for topics, users, preferences, briefings, items, item sources and generation runs. The repository isolates SQL behind a small interface so a future PostgreSQL repository can replace it.

## Orchestration

`BriefingOrchestrator` resolves the user's IANA timezone and local date, applies preferences, enforces the unique `(user_id, briefing_date)` boundary, consumes the Phase 3.3 adapter, persists the result and records generation metrics. HTTP retrieval never calls Ollama. The current dev generation endpoint loads the already-produced structured briefing; a future worker can call the engine asynchronously.

## Failure model

Generation failures persist a `FAILED` briefing and a structured error state. Retrieval returns that known state rather than a stack trace. Provider execution is intentionally outside GET request handling.

## Future boundaries

Phase 4.2 adds a scheduler/worker, shared profile editions and user deliveries without changing the engine boundary. Phase 4.3 adds an abstract local identity provider, authenticated client routes and onboarding. Future phases may add external identity, PostgreSQL, mobile clients and notifications.
