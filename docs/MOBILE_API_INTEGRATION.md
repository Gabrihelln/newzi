# Mobile API Integration

## Push API (Phase 4.7)

Authenticated device registration derives ownership from the current session: `POST /api/v1/me/devices` and `DELETE /api/v1/me/devices/{id}`. Notification preferences use `GET|PUT /api/v1/me/notification-settings`. Token refresh is idempotent. Logout disables registered devices but never blocks local logout if the network is unavailable.

The client uses register/login/logout, `/me`, `/me/onboarding`, `/me/preferences`, `/me/briefings/today`, paginated `/me/briefings` and `/client/config`. Every request goes through the central client, which adds the bearer token, parses the structured error contract, applies a timeout and maps network failures to `OFFLINE`.

The token is stored only behind the native `secureStorage` abstraction, backed by Android Keystore/iOS Keychain through `react-native-keychain`. A 401 clears local session state and returns to auth. Logout clears local state even if the network request fails. `today` never generates content; it reads persisted delivery state, reports audio generation separately, and keeps an older READY delivery playable where available. History resolves both new UserBriefingDelivery/BriefingEdition data and legacy persisted briefings through the compatible backend API.
## Audio API (Phase 4.6)

The client may call `GET /api/v1/me/briefings/{briefing_id}/audio` to read audio state; this is metadata-only and never generates audio. A READY response contains the persisted artifact URL, duration and structured segments, and READY requires a validated artifact bound to the same delivery, edition, script and selected voice. PENDING/GENERATING/FAILED audio states do not block the textual briefing or replace an older playable delivery. Development generation is restricted to explicit `/api/v1/dev/...` POST endpoints.
