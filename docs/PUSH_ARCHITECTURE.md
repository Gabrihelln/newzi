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

## Favourite teams and followed games (worker role `football`)

Esportes › Times favoritos stores favourite teams (`user_favorite_teams`; Básico 1, Premium 10) and the switches
`team_kickoff_enabled`, `team_goals_enabled`, `team_final_enabled` and `team_news_enabled` (migration 0009, on by
default). The bell on a game stores it in `user_followed_matches`. The `football` role (`football_alerts.py`) reads
football-data.org's game list every minute (the same cached call as the API) and compares each game someone cares
about with `football_match_states`: scheduled → in play sends `TEAM_KICKOFF`, a side's score going up `TEAM_GOAL`,
→ finished `TEAM_FINAL` (with the person's team place in the table). A game seen for the first time is only
recorded. Every five minutes, a football article from the last 3 h whose headline names a favourite team sends
`TEAM_NEWS` (at most `TEAM_NEWS_PER_DAY`, 3, per team, never in quiet hours). They use the Android channel
`team_alerts` ("Seu time"); game alerts open Esportes, news opens the story. Free-plan limits: no minute, scorers or
recent form from the provider (the table's last results are computed from the season's games).

## Announcements and promotions (Firebase console)

General announcements ("Novidades do Newzi") and promotions ("Ofertas e promoções") are not sent by the backend and have no switch in the app: every install joins the FCM topics `novidades` and `promocoes` on launch (`mobile/src/push/topics.ts`), so they reach everyone whose phone allows notifications, signed in or not, whatever the in-app switches say. On Android each has its own channel (`announcements`, `promotions`) that people can mute in the system settings.

Apple's App Store Review Guideline 4.5.4 requires explicit opt-in consent, shown in the app, before sending promotional pushes, and a way to opt out. Before sending promotions to iOS users, add that consent (and its opt-out) or limit promotion campaigns to Android.

To send one: Firebase console › Messaging › New campaign › Firebase Notification messages, then

1. write the title and text (free per campaign) and, optionally, an image;
2. target › **Topic** › `novidades` or `promocoes`;
3. Additional options › Android notification channel: `announcements` or `promotions`;
4. Additional options › Custom data (optional), what a tap opens: `type` = `ANNOUNCEMENT` or `PROMOTION`, and one of `screen` (`Subscription`, `NotificationSettings`, `ContentPreferences`, `DailyBriefing`, `Football`, `Search`, `History`), `story_id` (a story) or `url` (an `https://` page). Without them a tap just opens the app;
5. schedule or send now. To try it first, "Send test message" with one device token.

Quiet hours and frequency are up to whoever sends; nothing limits them automatically.

## Breaking news

The `breaking` worker role (`backend/src/newzi_backend/breaking.py`) checks every `BREAKING_CHECK_SECONDS` (5 min) for an event, meaning articles the clustering grouped under one `event_id`, that at least `BREAKING_MIN_SOURCES` (5) distinct sources published within the last `BREAKING_WINDOW_MINUTES` (90). The event qualifies only if none of its articles is older than that window, so only many outlets at once count, not an old story slowly gaining coverage, and only if its lead article is news: deals, guides, reviews, roundups, how-tos, explainers and opinion are skipped. Until 2026-10-19 the rule was 3 outlets in 180 minutes with no pacing, which with 220 sources sent too many pushes in a short time.

A user gets one `BREAKING_NEWS` job per active device when all of these hold:

- `notifications_enabled` and `breaking_news_enabled` are on;
- the event matches their topics (a followed domain covers its subjects; `content_scope=all` covers everything) and country scope (`GLOBAL` = foreign outlets plus the Brazilian world desks, `content.world_source_ids`);
- a Portuguese reader only gets a story with Portuguese coverage (`content.readable`): one covered only in English is never pushed, as it is never listed, put in a briefing or narrated;
- their local time is outside `BREAKING_QUIET_HOURS` (`22-7`).

Pacing keeps it from becoming noise:

- at least `BREAKING_MIN_GAP_MINUTES` (45) pass between two breaking pushes to the same user. A story found during the gap waits; each check sends the strongest story still breaking (most distinct sources) first, and a story that fell out of the window meanwhile is dropped;
- at most `BREAKING_DAILY_LIMIT` (5) a day per user, counted from midnight in their time zone; cancelled (stale) pushes do not count. Past the limit only a story covered by `BREAKING_EXCEPTIONAL_SOURCES` (10) outlets is still sent, after the gap like any other.

Each job stores its title (the lead headline, preferring a Portuguese source), its body and its data in `payload_json`. The body is a short summary of the story taken from the first useful article description (HTML and feed boilerplate removed, a repeated headline dropped, cut at a sentence end); without one it says "Toque para ler a matéria completa no Newzi." The outlets are no longer listed in the body. The data is `type=BREAKING_NEWS`, `event_id`, `story_id` and `url`. Jobs are unique per event and device, and the same story is not sent again within 24 h, whether under a new event id (re-clustering, a second wave of coverage) or because it already went out as a `TEAM_NEWS` alert, and the other way round (`already_told`: the earlier push carried one of the event's articles or the same headline). A team-news alert is keyed by the story's event, not by the article, so another outlet's article on the same story is not a new alert. They are delivered by the `notifications` role like daily briefings and are cancelled rather than sent once they are older than `BREAKING_MAX_DELAY_MINUTES` (60).

Development-only controls are `POST /api/v1/dev/notifications/enqueue` and `POST /api/v1/dev/notifications/run`; they are disabled when `APP_ENV=production`.

## Mobile

The React Native CLI app uses `@react-native-firebase/app@26.4.0` and `@react-native-firebase/messaging@26.4.0`, without Expo Notifications. Permission is asked in onboarding (step "Ative as notificações", where each notice is chosen) and from Profile › Notificações. Firebase's `requestPermission` never shows a prompt on Android, so Android 13+ asks for `POST_NOTIFICATIONS` through `PermissionsAndroid`; when the system no longer lets the app ask, the app's system settings open. The app obtains/refreshes the FCM token and registers it with the backend with the real app version, device locale, permission and install id. A tapped notification opens its screen (`DAILY_BRIEFING` → briefing player, `BREAKING_NEWS` → the story via `GET /api/v1/me/news/{story_id}`); a push that arrives while the app is open is not shown (the system hides it and the app shows no in-app notice). Android creates one channel per kind, `daily_briefing` (`Resumo diário`, default importance) and `breaking_news` (`Notícias urgentes`, high importance), and the backend sets `channel_id` per type so users can mute each in system settings. Profile › Notificações shows the system permission state on top (blue when everything works, orange with "Ativar permissão" when the phone blocks notifications), the main switch, and one switch per notice, each saving on its own (switch writes have their own 60/min limit per user). A real Firebase project still requires environment-specific `google-services.json`, intentionally absent from this repository.

Notification data contains only `type=DAILY_BRIEFING`, `briefing_id` and `delivery_id`. The app restores session first and then resolves the referenced briefing before opening its detail item. Foreground events use the same pending-briefing path; no duplicate local schedule is created.

## iOS and deferred scope

macOS setup requires `GoogleService-Info.plist`, Firebase Messaging/APNs configuration, Push Notifications capability, APNs key/certificate and Pods. Push runtime remains unvalidated on Windows. Marketing/promotional pushes, rich media, complex actions, payments, subscriptions, paywall, commercial analytics and social login remain out of scope.

## Device test matrix (Android and iOS)

Run on a real phone of each platform with a signed-in account (dev routes `POST /api/v1/dev/notifications/enqueue` and `/run`, or a Firebase test message):

| Case | Expected |
|---|---|
| Onboarding, "Ativar" with both notices on | system prompt appears (Android 13+ and iOS); refusing still finishes the onboarding and Profile › Notificações shows the orange "bloqueadas" card |
| Onboarding, "Agora não" | no prompt; both notices saved off |
| Push with the app open | nothing is shown, neither by the system nor inside the app |
| Push with the app in the background / closed | system notification with the Newzi icon; a tap opens the briefing or story after the session is restored |
| Permission turned off in the phone settings, back to the app | the screen turns orange; the device is reported `DENIED` and gets no pushes |
| Permission turned on again | the screen turns blue on return; pushes resume |
| Main switch off | the other switches fade but keep their value; queued pushes are cancelled |
| Same push sent twice | only one notification stays on screen (tag / collapse id) |
| Sign out, sign in with another account | the phone only receives the new account's pushes |
