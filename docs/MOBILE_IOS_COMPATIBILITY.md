# Mobile iOS Compatibility Checklist

## Dependencies added in Phase 4.5

| Package | Version | Android | iOS | Native setup | Pod/manual patch |
|---|---|---|---|---|---|
| @react-navigation/native | installed in package-lock | yes | yes | JS navigation container | no manual patch expected |
| @react-navigation/native-stack | installed in package-lock | yes | yes | native stack through react-native-screens | pod install/autolinking |
| @react-navigation/bottom-tabs | installed in package-lock | yes | yes | JS tab navigator | no manual patch expected |
| react-native-screens | installed in package-lock | yes | yes | autolinking | pod install; verify Xcode build |
| react-native-safe-area-context | installed in package-lock | yes | yes | autolinking | pod install; currently compatible dependency |
| react-native-keychain | installed in package-lock | yes | yes | Keystore-backed cipher storage / native module | pod install; verify Keychain entitlements only if required |

## Existing native preparation

- ios/Podfile uses React Native CocoaPods helpers and use_native_modules!.
- ios/NewsEngineNative/AppDelegate.swift starts the shared Newzi module. The Xcode folder/target keeps a legacy internal name temporarily to avoid a destructive Windows-side project rename.
- React Native CLI autolinking is used; Expo prebuild and Expo modules are absent.
- Android has only INTERNET permission and uses native Gradle autolinking.
- The iOS deployment target is inherited from the current React Native template and must be confirmed against the installed Xcode SDK.

## Mac execution checklist

1. Run npm install and pod install from mobile/ios.
2. Open the generated Xcode workspace in Xcode; the installed product and bundle identifier are Newzi / com.newzi.app.
3. Confirm deployment target, Swift version and New Architecture settings.
4. Confirm react-native-keychain pod compiles and Keychain access works on Simulator and iPhone.
5. Build Debug and Release with signing configured.
6. Execute the same Auth, onboarding, Today, detail/source, history, preferences, restart and logout flows.

## Phase 4.6 audio track

- Library: `react-native-sound@0.11.2`.
- Autolinking: enabled through React Native CLI integration; CocoaPods integration is prepared by the library podspec.
- iOS deployment target: inherited from the current React Native Podfile (`min_ios_version_supported`).
- Background audio: foreground playback is prepared; background/remote-control policy is deferred.
- Info.plist: playback requires no microphone or recording permission; final background-mode decision belongs to macOS/Xcode validation.
- Known limitation: iOS build, Pods and runtime remain NOT_EXECUTED on Windows.

Current gates: IOS_IMPLEMENTATION_PREPARED = YES, IOS_AUDIO_IMPLEMENTATION_PREPARED = YES, IOS_BUILD_PASS = NOT_EXECUTED, IOS_AUDIO_RUNTIME_PASS = NOT_EXECUTED, IOS_RUNTIME_PASS = NOT_EXECUTED. No feature requires an Android-only implementation.

## Phase 4.7 push track

- Libraries: `@react-native-firebase/app@26.4.0` and `@react-native-firebase/messaging@26.4.0`.
- Android requires environment-specific `google-services.json`, FCM project registration and `POST_NOTIFICATIONS` runtime permission handling.
- iOS requires `GoogleService-Info.plist`, Firebase Messaging Pods, APNs key/certificate, Push Notifications capability and AppDelegate/APNs registration validation.
- Background Modes must be decided only when background delivery is needed; notification-open handling is prepared but not runtime-validated.
- No Firebase credentials are present in the repository; iOS build/runtime remain NOT_EXECUTED on Windows.
