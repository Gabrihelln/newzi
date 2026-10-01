# Scheduler Architecture

> Para operação contínua, use `python engine/main.py --worker` a partir da raiz. Esse worker coordena scheduler, composição, áudio e notificação. `--scheduler` continua disponível para operação isolada; consulte o `README.md`.

`BriefingScheduler` is a coordinator only. It loads active users and preferences, resolves the IANA local date, subtracts `BRIEFING_GENERATION_LEAD_MINUTES` (default 30), and creates one `GenerationJob` per user/date. It never calls the engine or Ollama.

The job stores both `scheduled_for` (UTC instant) and the local `delivery_time`/`timezone`. Repeated scheduler runs are idempotent. `Clock`/`FixedClock` make DST and boundary tests deterministic; no manual UTC offsets are used.

Commands:

```text
python engine/main.py --scheduler-once
python engine/main.py --worker-once
```

The scheduler does not create duplicate jobs for users with the same profile. Each user has a delivery job, while the worker deduplicates the editorial edition by `profile_key + edition_date`.

After onboarding or preference changes, the same scheduler path reads the updated preference row and calculates future eligibility using the new local time/timezone. Existing historical deliveries are not rewritten.
