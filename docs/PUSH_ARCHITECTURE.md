# NEWS ENGINE - PUSH ARCHITECTURE (PHASE 4.7)

## Boundary and provider

The Product Backend owns delivery eligibility and notification jobs. `PushProvider` exposes `send(token, title, body, data)` and returns success, provider message id, retryability and invalid-token classification. Development uses `DevelopmentPushProvider`, which records safe local sends. `FCMPushProvider` is the production boundary: it sends through the Firebase Admin SDK (`firebase_admin.messaging`) with the service account in `GOOGLE_APPLICATION_CREDENTIALS`, which refreshes OAuth tokens itself, and an optional `FCM_PROJECT_ID` (defaults to `FIREBASE_PROJECT_ID`); no credentials or tokens are committed.

Firebase scope is messaging only. Product identity, database, scheduler, briefings and audio remain in the existing Product Backend.

## Devices and settings

`push_devices` supports multiple ANDROID/IOS devices per user, unique tokens, enabled/invalidated state, app version, locale, timezone and last-seen timestamps. Authenticated routes derive `user_id` from the bearer session and never trust a client-supplied user id. Responses never return the full push token.

The app registers its install at sign-in, on every return to the foreground (only when the token or the permission changed) and on token refresh, sending:

- `permission`: the system permission (`AUTHORIZED`, `PROVISIONAL`, `DENIED`, `NOT_DETERMINED`). A phone where notifications are blocked stays linked to the account but is disabled, and its pending jobs are cancelled, until it reports the permission again;
- `device_identifier`: the install's id. A new token from the same phone (reinstall, rotation) retires the older rows, so one push never arrives twice.

`notification_settings` is separate from editorial preferences: `notifications_enabled` (main switch), `daily_briefing_enabled` and `breaking_news_enabled` (off by default; onboarding asks for each). `GET|PUT /api/v1/me/notification-settings` also returns what the screen shows next to the switches: `briefing_time`, `briefing_size`, `breaking_news_rules` (`max_per_day`, `quiet_hours`) and `active_devices`. A PUT must carry at least one of the three switches, as booleans.

Routes: `POST /api/v1/me/devices`, `DELETE /api/v1/me/devices/{device_id}` and `GET|PUT /api/v1/me/notification-settings`.

## Notification types

`NOTIFICATION_KINDS` in `notifications.py` is the catalog: every push the backend sends, the switch that allows it, its Android channel and how long it stays useful (FCM/APNs expiry).

| `data.type` | Switch | Android channel | Title | Body | Tap opens | Expires |
|---|---|---|---|---|---|---|
| `DAILY_BRIEFING` | `daily_briefing_enabled` | `daily_briefing` | "Seu resumo de hoje está pronto" | "10 notícias selecionadas para você · 5 min" (items and audio length of the edition) | the briefing player (`briefing_id`) | 3 h |
| `BREAKING_NEWS` | `breaking_news_enabled` | `breaking_news` | the lead headline | a short summary of the story (`story_summary`, at most 160 characters) | the story (`story_id`) | 1 h |

Every push also needs `notifications_enabled`. The switches are checked when a job is queued and again right before it is sent, so a notice turned off in between is cancelled. Each push carries a tag (the delivery or event id) used as Android `tag`/`collapse_key` and APNs `apns-collapse-id`: a resend replaces the notification already shown instead of stacking a copy. Android shows the one-color Newzi symbol (`res/drawable/ic_notification.xml`) in the brand blue; a breaking push with an HTTPS article image shows it on Android.

## Delivery timing and jobs

`NotificationService.enqueue_ready` creates one `DAILY_BRIEFING` job per active device only after the delivery is READY for its selected voice and references a validated audio artifact and narration script for the same edition. The job is unique by delivery, device and notification type. `scheduled_for` uses the delivery's local IANA timezone and `briefing_time`; generation lead time does not move push earlier. A 30-minute late-delivery tolerance admits READY deliveries that finish shortly after the target. `run_once` revalidates the persisted delivery and media file immediately before sending, retries transient failures with bounded backoff and disables invalid tokens. One device failure does not prevent other devices.

## Breaking news

The `breaking` worker role (`backend/src/newzi_backend/breaking.py`) checks every `BREAKING_CHECK_SECONDS` (5 min) for an event, meaning articles the clustering grouped under one `event_id`, that at least `BREAKING_MIN_SOURCES` (3) distinct sources published within the last `BREAKING_WINDOW_MINUTES` (180). The event qualifies only if none of its articles is older than that window, so an old story gaining coverage does not count, and only if its lead article is news: deals, guides, reviews, roundups, how-tos, explainers and opinion are skipped. On the development data this fired about once every two days.

A user gets one `BREAKING_NEWS` job per active device when all of these hold:

- `notifications_enabled` and `breaking_news_enabled` are on;
- the event matches their topics (or `content_scope=all`) and country scope;
- their local time is outside `BREAKING_QUIET_HOURS` (`22-7`);
- they received fewer than `BREAKING_MAX_PER_DAY` (2) breaking pushes in the last 24 h and none in the last `BREAKING_MIN_GAP_MINUTES` (180).

Each job stores its title (the lead headline, preferring a Portuguese source), its body and its data in `payload_json`. The body is a short summary of the story taken from the first useful article description (HTML and feed boilerplate removed, a repeated headline dropped, cut at a sentence end); without one it says "Toque para ler a matéria completa no Newzi." The outlets are no longer listed in the body. The data is `type=BREAKING_NEWS`, `event_id`, `story_id` and `url`. Jobs are unique per event and device, and the same story is not sent again under a new event id (re-clustering, a second wave of coverage) within 24 h. They are delivered by the `notifications` role like daily briefings and are cancelled rather than sent once they are older than `BREAKING_MAX_DELAY_MINUTES` (60).

Development-only controls are `POST /api/v1/dev/notifications/enqueue` and `POST /api/v1/dev/notifications/run`; they are disabled when `APP_ENV=production`.

## Mobile

The React Native CLI app uses `@react-native-firebase/app@26.4.0` and `@react-native-firebase/messaging@26.4.0`, without Expo Notifications. Permission is asked in onboarding (step "Ative as notificações", where each notice is chosen) and from Profile › Notificações. Firebase's `requestPermission` never shows a prompt on Android, so Android 13+ asks for `POST_NOTIFICATIONS` through `PermissionsAndroid`; when the system no longer lets the app ask, the app's system settings open. The app obtains/refreshes the FCM token and registers it with the backend with the real app version, device locale, permission and install id. A tapped notification opens its screen (`DAILY_BRIEFING` → briefing player, `BREAKING_NEWS` → the story via `GET /api/v1/me/news/{story_id}`); a push that arrives while the app is open is shown as an in-app notice. Android creates one channel per kind, `daily_briefing` (`Resumo diário`, default importance) and `breaking_news` (`Notícias urgentes`, high importance), and the backend sets `channel_id` per type so users can mute each in system settings. Profile › Notificações shows the system permission state on top (blue when everything works, orange with "Ativar permissão" when the phone blocks notifications), the main switch, and one switch per notice, each saving on its own (switch writes have their own 60/min limit per user). A real Firebase project still requires environment-specific `google-services.json`, intentionally absent from this repository.

Notification data contains only `type=DAILY_BRIEFING`, `briefing_id` and `delivery_id`. The app restores session first and then resolves the referenced briefing before opening its detail item. Foreground events use the same pending-briefing path; no duplicate local schedule is created.

## iOS and deferred scope

macOS setup requires `GoogleService-Info.plist`, Firebase Messaging/APNs configuration, Push Notifications capability, APNs key/certificate and Pods. Push runtime remains unvalidated on Windows. Marketing/promotional pushes, rich media, complex actions, payments, subscriptions, paywall, commercial analytics and social login remain out of scope.

## Device test matrix (Android and iOS)

Run on a real phone of each platform with a signed-in account (dev routes `POST /api/v1/dev/notifications/enqueue` and `/run`, or a Firebase test message):

| Case | Expected |
|---|---|
| Onboarding, "Ativar" with both notices on | system prompt appears (Android 13+ and iOS); refusing still finishes the onboarding and Profile › Notificações shows the orange "bloqueadas" card |
| Onboarding, "Agora não" | no prompt; both notices saved off |
| Push with the app open | in-app notice at the top; a tap opens the briefing or story |
| Push with the app in the background / closed | system notification with the Newzi icon; a tap opens the briefing or story after the session is restored |
| Permission turned off in the phone settings, back to the app | the screen turns orange; the device is reported `DENIED` and gets no pushes |
| Permission turned on again | the screen turns blue on return; pushes resume |
| Main switch off | the other switches fade but keep their value; queued pushes are cancelled |
| Same push sent twice | only one notification stays on screen (tag / collapse id) |
| Sign out, sign in with another account | the phone only receives the new account's pushes |
