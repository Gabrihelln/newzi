# NEWS ENGINE system architecture

```text
Sources
  -> collection and normalization
  -> deterministic filtering/dedup/ranking
  -> semantic classification and conservative routing
  -> factual summarization and evidence validation
  -> BriefingEdition
  -> UserBriefingDelivery
  -> optional AudioScript/AudioArtifact
  -> NotificationJob/provider
  -> React Native mobile client
```

The engine owns source collection, event intelligence and editorial output. The product backend owns identity, preferences, scheduling, delivery history, API contracts and job persistence. Audio is an optional server-side artifact pipeline; mobile only requests and plays ready artifacts. Push is an optional delivery channel with server-side provider abstraction, device ownership checks and idempotent jobs. SQLite is the current single-node persistence boundary.

Environment configuration is centralized in `ProductConfig`; mobile receives an explicit build-time environment/API boundary. DEV routes are operational tooling and are unavailable in production. UI remains functional/provisional until a separate visual design phase.
# Editorial language and topic contract

News Engine separates `source_language`, `output_language`, and geographic
`scope`. A source may be English while a profile requests `output_language=pt-BR`.
Before persistence, the item must pass the output-language gate. Deterministic
fallback is source-bound and cannot copy non-Portuguese evidence into a pt-BR
briefing; it backfills with a compatible Portuguese event or skips the event.

The canonical topic registry is `app/topic_registry.py`. Product Backend exposes
the enabled subset through `/api/v1/topics`; mobile renders that response and
does not maintain an editorial topic list. `BRAZIL` is an editorial topic,
while `scope=BRAZIL` is a geographic preference and they are not interchangeable.

Item metadata distinguishes `source_language`, `output_language`,
`summary_provider`, `localization_provider`, `localization_applied`, and
`language_gate`. Profile schema versioning prevents reuse of an edition created
under an incompatible editorial contract.
