# Scaling boundaries

The current SQLite product database is suitable for local development and a single-node MVP. It uses schema versions, unique keys for idempotency, foreign keys and application-level job claims.

Known boundaries:

- SQLite locking limits concurrent scheduler/worker writers.
- In-memory auth rate limiting is per process and is not shared across instances.
- Local audio storage is node-local and is not a CDN or durable object store.
- Multiple API/worker instances require a shared database, a distributed job claim/lock and shared object storage.
- PostgreSQL becomes the appropriate next step when write concurrency, HA, replicas, or multi-instance workers are required.

Do not scale by simply starting more workers against the same SQLite file.
