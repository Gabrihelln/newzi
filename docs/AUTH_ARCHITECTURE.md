# Identity and Session Architecture

Phase 4.3 uses an `IdentityProvider` abstraction. `LocalIdentityProvider` is the development implementation; a future external provider can implement the same `authenticate`, `resolve` and `revoke` contract without entering engine code.

Passwords are never returned or stored in plaintext. The local provider uses salted PBKDF2-HMAC-SHA256 from Python's standard library. Sessions are opaque random tokens; only their SHA-256 digest is stored in `auth_sessions`, with creation, expiration and revocation timestamps. A disabled user invalidates existing sessions through the central resolver.

`ProductAPI` resolves the bearer token once and uses that identity for all `/me` resources. Legacy user-id endpoints remain for compatibility, but an authenticated token cannot access another user's resource. Public responses use `ProductRepository.public_user`, which removes password fields.

Register/login have a small in-process rate-limit boundary. This is local development protection, not distributed production rate limiting.

## Firebase Authentication (Phase 6.1)

The active product path uses Firebase Authentication. The mobile obtains a Firebase ID token and sends it as an Authorization Bearer token; the backend verifies it with Firebase Admin and derives the user from the verified UID. No QA account or QA CTA is shipped. The older local provider is retained only for isolated legacy tests until real Firebase runtime validation completes.
