# Newzi Firebase architecture — Phase 6.1

Firebase Authentication is the identity authority. The mobile uses email/password Auth and sends the current Firebase ID token as Authorization Bearer to the Product Backend. The backend verifies that token with Firebase Admin; it never trusts a client-supplied user ID.

The Product Backend is the only store of profile data, onboarding, preferences and notification settings. The display name lives in Firebase Auth and reaches the backend in the ID token. The app no longer uses Firestore (the `users/{firebaseUid}` mirror was write-only and could drift from the backend); existing documents can be deleted.

News, events, briefings, audio, deliveries, jobs, and scheduler state remain in the Product Backend/SQLite. Firebase does not replace the operational database.

The backend keeps its internal user row for operational foreign keys and adds firebase_uid as a unique external identity key. New Firebase users use their Firebase UID as the row ID. Passwords, Firebase tokens, refresh tokens, and service-account material are never persisted.

The Firestore rules in firebase/firestore.rules are kept only for existing data; nothing in the app reads or writes Firestore.
