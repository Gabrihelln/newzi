# NEWS ENGINE - PUSH ARCHITECTURE (PHASE 4.7)

## Boundary and provider

The Product Backend owns delivery eligibility and notification jobs. `PushProvider` exposes `send(token, title, body, data)` and returns success, provider message id, retryability and invalid-token classification. Development uses `DevelopmentPushProvider`, which records safe local sends. `FCMPushProvider` is the production boundary and reads `FCM_PROJECT_ID`/`FCM_ACCESS_TOKEN` from the environment; no credentials or tokens are committed.

Firebase scope is messaging only. Product identity, database, scheduler, briefings and audio remain in the existing Product Backend.

## Devices and settings

`push_devices` supports multiple ANDROID/IOS devices per user, unique tokens, enabled/invalidated state, app version, locale, timezone and last-seen timestamps. Authenticated routes derive `user_id` from the bearer session and never trust a client-supplied user id. Responses never return the full push token.

`notification_settings` is separate from editorial preferences. Phase 4.7 implements `notifications_enabled` and `daily_briefing_enabled`; breaking news is stored only as a disabled future field.

Routes: `POST /api/v1/me/devices`, `DELETE /api/v1/me/devices/{device_id}` and `GET|PUT /api/v1/me/notification-settings`.

## Delivery timing and jobs

`NotificationService.enqueue_ready` creates one `DAILY_BRIEFING` job per active device only after the delivery is READY for its selected voice and references a validated audio artifact and narration script for the same edition. The job is unique by delivery, device and notification type. `scheduled_for` uses the delivery's local IANA timezone and `briefing_time`; generation lead time does not move push earlier. A 30-minute late-delivery tolerance admits READY deliveries that finish shortly after the target. `run_once` revalidates the persisted delivery and media file immediately before sending, retries transient failures with bounded backoff and disables invalid tokens. One device failure does not prevent other devices.

Development-only controls are `POST /api/v1/dev/notifications/enqueue` and `POST /api/v1/dev/notifications/run`; they are disabled when `APP_ENV=production`.

## Mobile

The React Native CLI app uses `@react-native-firebase/app@26.4.0` and `@react-native-firebase/messaging@26.4.0`, without Expo Notifications. It requests permission contextually from Preferences, obtains/refreshes the FCM token, registers it with the backend and handles notification-open events. Android creates the `daily_briefing` channel (`Briefing diário`, `IMPORTANCE_DEFAULT`) and declares `POST_NOTIFICATIONS`. A real Firebase project still requires environment-specific `google-services.json`, intentionally absent from this repository.

Notification data contains only `type=DAILY_BRIEFING`, `briefing_id` and `delivery_id`. The app restores session first and then resolves the referenced briefing before opening its detail item. Foreground events use the same pending-briefing path; no duplicate local schedule is created.

## iOS and deferred scope

macOS setup requires `GoogleService-Info.plist`, Firebase Messaging/APNs configuration, Push Notifications capability, APNs key/certificate and Pods. Push runtime remains unvalidated on Windows. Breaking/marketing/promotional pushes, rich media, complex actions, payments, subscriptions, paywall, commercial analytics and social login remain out of scope.
