# Mobile Architecture - Phase 4.5

The client in mobile/ is one shared React Native CLI + TypeScript codebase for Android and iOS. Android is a native Gradle project and iOS is a native Xcode/CocoaPods project. Expo, Expo Go, EAS and expo-* runtime dependencies are not used.

App.tsx owns bootstrap only: secure session restoration, /me validation, onboarding redirect, auth redirect, 401 handling and logout. src/navigation/RootNavigator.tsx owns the Auth, Onboarding and Main flows. The Main flow uses a native stack with bottom tabs for Hoje, Histórico and Preferências, plus a dedicated Detail route.

src/api/client.ts is the only HTTP boundary and contains V1 endpoint access, bearer auth, timeout and structured error mapping. src/storage/secureStorage.ts isolates react-native-keychain (Android Keystore / iOS Keychain). src/config/env.ts owns development, staging and production API hosts. src/config/timezone.ts uses the IANA timezone exposed by Intl with a safe fallback.

The small design system is in src/theme/index.ts, with colors, surfaces, spacing, typography, radius, elevation, states and accessibility sizing. Reusable primitives live in src/components/ui.tsx. Product screens remain intentionally light and editorial rather than administrative.
## Audio foundation (Phase 4.6)

## Push foundation (Phase 4.7)

Push uses React Native Firebase Messaging, not Expo. Permission is requested from Preferences, the FCM token is registered through the authenticated Product API, token refresh re-registers the device, and notification-open data carries a daily briefing target. Android channel creation and `POST_NOTIFICATIONS` are configured; Firebase project files remain environment-specific and are not committed.

The mobile layer consumes audio metadata from the product API and delegates playback to `src/audio/player.ts`, backed by `react-native-sound@0.11.2`. The player is not an editorial engine: it does not summarize, generate scripts or synthesize speech. It exposes foreground play/pause, restart, seek and progress controls and renders non-blocking `NOT_AVAILABLE`, `PENDING`, `GENERATING`, `READY`, `FAILED` and `OFFLINE` states.
