# NEWS ENGINE - PUSH ARCHITECTURE (PHASE 4.7)

## Boundary and provider

The Product Backend owns delivery eligibility and notification jobs. `PushProvider` exposes `send(token, title, body, data)` and returns success, provider message id, retryability and invalid-token classification. Development uses `DevelopmentPushProvider`, which records safe local sends. `FCMPushProvider` is the production boundary: it sends through the Firebase Admin SDK (`firebase_admin.messaging`) with the service account in `GOOGLE_APPLICATION_CREDENTIALS`, which refreshes OAuth tokens itself, and an optional `FCM_PROJECT_ID` (defaults to `FIREBASE_PROJECT_ID`); no credentials or tokens are committed.

Firebase scope is messaging only. Product identity, database, scheduler, briefings and audio remain in the existing Product Backend.

## Devices and settings

`push_devices` supports multiple ANDROID/IOS devices per user, unique tokens, enabled/invalidated state, app version, locale, timezone and last-seen timestamps. Authenticated routes derive `user_id` from the bearer session and never trust a client-supplied user id. Responses never return the full push token.

`notification_settings` is separate from editorial preferences: `notifications_enabled` (master switch), `daily_briefing_enabled` and `breaking_news_enabled` (opt-in, off by default).

Routes: `POST /api/v1/me/devices`, `DELETE /api/v1/me/devices/{device_id}` and `GET|PUT /api/v1/me/notification-settings`.

## Delivery timing and jobs

`NotificationService.enqueue_ready` creates one `DAILY_BRIEFING` job per active device only after the delivery is READY for its selected voice and references a validated audio artifact and narration script for the same edition. The job is unique by delivery, device and notification type. `scheduled_for` uses the delivery's local IANA timezone and `briefing_time`; generation lead time does not move push earlier. A 30-minute late-delivery tolerance admits READY deliveries that finish shortly after the target. `run_once` revalidates the persisted delivery and media file immediately before sending, retries transient failures with bounded backoff and disables invalid tokens. One device failure does not prevent other devices.

## Breaking news

The `breaking` worker role (`backend/src/newzi_backend/breaking.py`) checks every `BREAKING_CHECK_SECONDS` (5 min) for an event, meaning articles the clustering grouped under one `event_id`, that at least `BREAKING_MIN_SOURCES` (3) distinct sources published within the last `BREAKING_WINDOW_MINUTES` (180). The event qualifies only if none of its articles is older than that window, so an old story gaining coverage does not count, and only if its lead article is news: deals, guides, reviews, roundups, how-tos, explainers and opinion are skipped. On the development data this fired about once every two days.

A user gets one `BREAKING_NEWS` job per active device when all of these hold:

- `notifications_enabled` and `breaking_news_enabled` are on;
- the event matches their topics (or `content_scope=all`) and country scope;
- their local time is outside `BREAKING_QUIET_HOURS` (`22-7`);
- they received fewer than `BREAKING_MAX_PER_DAY` (2) breaking pushes in the last 24 h and none in the last `BREAKING_MIN_GAP_MINUTES` (180).

Each job stores its title (the lead headline, preferring a Portuguese source), its body ("<source> e mais N veículos estão cobrindo esta notícia") and its data in `payload_json`. The data is `type=BREAKING_NEWS`, `event_id`, `story_id` and `url`. Jobs are unique per event and device, are delivered by the `notifications` role like daily briefings, and are cancelled rather than sent once they are older than `BREAKING_MAX_DELAY_MINUTES` (60).

The mobile app does not expose a breaking-news toggle yet. A tap on a breaking-news push opens the app without navigating to the story.

Development-only controls are `POST /api/v1/dev/notifications/enqueue` and `POST /api/v1/dev/notifications/run`; they are disabled when `APP_ENV=production`.

## Mobile

The React Native CLI app uses `@react-native-firebase/app@26.4.0` and `@react-native-firebase/messaging@26.4.0`, without Expo Notifications. It requests permission contextually from Preferences, obtains/refreshes the FCM token and registers it with the backend with the real app version and device locale. A tapped notification opens its screen (`DAILY_BRIEFING` → briefing player, `BREAKING_NEWS` → the story via `GET /api/v1/me/news/{story_id}`); a push that arrives while the app is open is shown as an in-app notice. Android creates one channel per kind, `daily_briefing` (`Briefing diário`, default importance) and `breaking_news` (`Notícias urgentes`, high importance), and the backend sets `channel_id` per type so users can mute each in system settings. Settings expose independent switches: all notifications, daily briefing and breaking news. A real Firebase project still requires environment-specific `google-services.json`, intentionally absent from this repository.

Notification data contains only `type=DAILY_BRIEFING`, `briefing_id` and `delivery_id`. The app restores session first and then resolves the referenced briefing before opening its detail item. Foreground events use the same pending-briefing path; no duplicate local schedule is created.

## iOS and deferred scope

macOS setup requires `GoogleService-Info.plist`, Firebase Messaging/APNs configuration, Push Notifications capability, APNs key/certificate and Pods. Push runtime remains unvalidated on Windows. Marketing/promotional pushes, rich media, complex actions, payments, subscriptions, paywall, commercial analytics and social login remain out of scope.
