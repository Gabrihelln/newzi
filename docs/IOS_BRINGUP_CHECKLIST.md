# iOS bring-up checklist

- [ ] Use Node 22.11+ and run `npm ci` from `mobile/`.
- [ ] Add the environment-specific `GoogleService-Info.plist`; never add server credentials.
- [ ] From `mobile/`, run `cd ios && pod install` and open the generated `.xcworkspace`.
- [ ] Confirm deployment target 15.1, Swift/New Architecture settings and bundle identifier.
- [ ] Enable Keychain capability and Push Notifications capability.
- [ ] Configure APNs key/certificate in Firebase for the matching bundle ID.
- [ ] Verify staging/production API URL is not localhost or emulator-only.
- [ ] Build simulator, then physical device; validate session restore, navigation and safe area.
- [ ] Validate briefing history, audio foreground playback, notification foreground/background/terminated and tap navigation.
- [ ] Verify Google OAuth Client ID and native Apple sign-in on a real device; the current iOS Firebase config and OAuth ID are not present in the repository.
- [ ] Configure signing/provisioning, archive and App Store export.

This is a bring-up checklist, not a claim that iOS build or runtime has passed.
