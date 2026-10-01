# Generation Worker

> Nota histórica: para a arquitetura operacional atual, consulte o `README.md` da raiz. O worker agora tem `run_batch` e `run_forever`; `EngineBriefingGenerator` compõe a partir do índice reutilizável e não invoca a fase 3.3 por perfil.

`BriefingGenerationWorker` claims one pending/retry job using `BEGIN IMMEDIATE` and a conditional status update. A second worker cannot claim the same job. Stale `RUNNING` jobs older than `WORKER_JOB_TIMEOUT_MINUTES` are moved to `RETRY`.

The worker loads preferences, creates a deterministic `BriefingProfile`, checks for a ready shared `BriefingEdition`, and otherwise calls the injected `BriefingGenerator`. `FixtureBriefingGenerator` is deterministic for tests/dev. `EngineBriefingGenerator` indexes changed content and composes from the shared index; optional Phase 3.3 output can be imported as cached enrichment.

Failures are classified as `PROVIDER_TIMEOUT`, `PROVIDER_UNAVAILABLE`, `ENGINE_FAILED`, `INSUFFICIENT_VALID_ITEMS`, `DATABASE_ERROR` or `UNKNOWN` by the generator boundary. Retry is bounded by `GENERATION_MAX_RETRIES` (default 2) with simple exponential backoff. No invalid edition is published.
