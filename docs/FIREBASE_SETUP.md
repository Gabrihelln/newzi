# Firebase setup — Phase 6.1

1. Create or select the development Firebase project.
2. Enable Email/Password under Authentication.
3. Create a Cloud Firestore database in production mode.
4. Add the Android application with application ID com.newzi.app.
5. Add the iOS application using the bundle identifier from the Xcode target.
6. Place the environment-specific google-services.json under mobile/android/app/ and GoogleService-Info.plist in the iOS target. These files are intentionally absent from this repository until the project is selected.
7. Configure the backend with FIREBASE_AUTH_ENABLED=true, FIREBASE_PROJECT_ID, and a protected GOOGLE_APPLICATION_CREDENTIALS path. Never commit the service-account JSON or private key.
8. Deploy firestore.rules through the Firebase CLI from the selected project.

The current workspace has no Firebase client configuration files, so Android/iOS runtime gates and Firebase Console confirmation remain pending. The local development API is not a substitute for Firebase runtime validation.
