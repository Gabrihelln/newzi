# NEWS ENGINE - AUDIO ARCHITECTURE (PHASE 4.6)

## Boundary

The engine/backend composes the editorial audio script from a persisted `BriefingEdition`. The mobile client never summarizes or invents editorial content; it consumes briefing data and audio metadata.

## Script and persistence

`audio_scripts` stores one versioned script per edition/language. `audio_script_segments` stores INTRO, TRANSITION, ITEM and OUTRO segments, related `briefing_item_id` when available, text and estimated duration. Exact segment timestamps remain nullable because the local provider does not guarantee timing.

The default target is 300 seconds. It is guidance, not an exact promise; estimated and actual duration are stored separately.

## Provider and storage

`TTSProvider` is the provider boundary. `LocalTTSProvider` uses optional local `pyttsx3`/system voices for development. A missing local dependency produces a structured FAILED audio job and never invalidates the textual briefing. `AudioStorage` is the migration boundary for object storage/CDN. SQLite stores metadata/path/checksum, not audio blobs.

## Jobs, reuse and observability

`audio_generation_jobs` is unique by edition, language, voice and script version. `AudioService.request` only enqueues/returns metadata; GET never synthesizes. `generate_pending` performs the asynchronous step. `audio_artifacts` is unique by the same configuration, enabling shared edition reuse. Events record requested, started, completed and failed transitions with low-cardinality metrics.

## API

- `GET /api/v1/me/briefings/{briefing_id}/audio` returns audio metadata and state.
- `GET /api/v1/me/briefings/{briefing_id}/audio/file` streams a ready local artifact.
- `POST /api/v1/dev/briefings/{id}/audio/generate` requests a development job only.
- `POST /api/v1/dev/audio/run` executes one pending development audio job.

Text briefings remain usable if audio fails. Historical audio is looked up only when an artifact exists; old briefings are not generated automatically.

## Mobile

The React Native client uses `react-native-sound@0.11.2`, with a `src/audio/player.ts` abstraction and a functional foreground `AudioPlayer` UI. It supports play/pause, restart, ±15 second seek, progress and duration, with explicit unavailable/pending/failure/offline states. Background controls and remote commands are deferred.

## Deferred

No push, downloads, podcast feed, CarPlay/Android Auto, advanced speed control, sleep timer, playlist, payments, subscription or analytics were added. A real provider with stable voice and background policy is required before production.
