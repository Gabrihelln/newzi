# Newzi Firebase architecture — Phase 6.1

Firebase Authentication is the identity authority. The mobile uses email/password Auth and sends the current Firebase ID token as Authorization Bearer to the Product Backend. The backend verifies that token with Firebase Admin; it never trusts a client-supplied user ID.

Firestore is the source of truth for user profile, onboarding, preferences, and notification preference at users/{firebaseUid}. The initial document contains uid, email, displayName, onboardingCompleted, server timestamps, a nested preferences map, and a nested notifications map.

News, events, briefings, audio, deliveries, jobs, and scheduler state remain in the Product Backend/SQLite. Firebase does not replace the operational database.

The backend keeps its internal user row for operational foreign keys and adds firebase_uid as a unique external identity key. New Firebase users use their Firebase UID as the row ID. Passwords, Firebase tokens, refresh tokens, and service-account material are never persisted.

Firestore rules are in firestore.rules and restrict each user to their own document and devices subcollection.
