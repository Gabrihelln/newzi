"""Firebase Admin identity boundary.

The Admin SDK is loaded only when Firebase authentication is enabled. Local
identity remains available for isolated legacy/unit tests until real Firebase
runtime validation is complete.
"""
from .identity import Identity, IdentityProvider
import hashlib
import logging
import os
import threading
import time

log = logging.getLogger("newzi.firebase_auth")


class FirebaseAdminIdentityProvider(IdentityProvider):
    def __init__(self, repo, project_id=""):
        self.repo = repo
        self._state = threading.local()
        self.project_id = project_id or None
        try:
            import firebase_admin
            from firebase_admin import auth
            if not firebase_admin._apps:
                firebase_admin.initialize_app(options={"projectId": self.project_id} if self.project_id else None)
            self.auth = auth
        except Exception as exc:
            raise RuntimeError("Firebase Admin SDK is required when FIREBASE_AUTH_ENABLED is enabled") from exc
        self.last_verify_reason = None
        # Verified tokens are reused briefly: verify_id_token(check_revoked=True) calls Google on
        # every request. A revocation therefore takes effect within this many seconds (0 disables).
        self.cache_seconds = max(0, int(os.getenv("FIREBASE_TOKEN_CACHE_SECONDS", "60")))
        self._verified = {}; self._verified_lock = threading.Lock()

    def _cached(self, key):
        with self._verified_lock:
            entry = self._verified.get(key)
            if entry and entry[0] > time.time(): return entry[1]
            self._verified.pop(key, None); return None

    def _remember(self, key, decoded):
        if not self.cache_seconds: return
        expires = min(time.time() + self.cache_seconds, float(decoded.get("exp") or 0))
        with self._verified_lock:
            if len(self._verified) >= 10_000:
                now = time.time(); self._verified = {k: v for k, v in self._verified.items() if v[0] > now}
                if len(self._verified) >= 10_000: self._verified.clear()
            self._verified[key] = (expires, {k: decoded.get(k) for k in ("uid", "email", "name")})

    @property
    def last_verify_reason(self):
        # Per-thread: concurrent requests must not read each other's verification result.
        return getattr(self._state, "reason", None)

    @last_verify_reason.setter
    def last_verify_reason(self, value):
        self._state.reason = value

    def authenticate(self, credentials):
        raise PermissionError("Firebase Authentication must be performed by the client")

    def resolve(self, token):
        if not token:
            self.last_verify_reason = "AUTH_EMPTY_TOKEN"
            return None
        key = hashlib.sha256(token.encode()).hexdigest()
        decoded = self._cached(key)
        if decoded is not None:
            self.last_verify_reason = None
            user = self.repo.ensure_firebase_user(decoded["uid"], decoded.get("email") or "", decoded.get("name") or "", self.account_exists)
            return Identity(user) if user else None
        try:
            # Firebase issues tokens using its own clock. A small leeway avoids
            # rejecting a freshly minted token when this host is a few seconds behind.
            decoded = self.auth.verify_id_token(token, check_revoked=True, clock_skew_seconds=5)
        except Exception as exc:
            name = type(exc).__name__
            lower = str(exc).lower()
            detail = str(exc).replace(token, "[REDACTED_TOKEN]")[:240]
            if "expired" in lower or "expired" in name.lower(): reason = "AUTH_FIREBASE_EXPIRED_TOKEN"
            elif "revoked" in lower or "revoked" in name.lower(): reason = "AUTH_FIREBASE_REVOKED_TOKEN"
            elif "project" in lower or "audience" in lower or "issuer" in lower: reason = "AUTH_FIREBASE_PROJECT_MISMATCH"
            elif "certificate" in lower: reason = "AUTH_FIREBASE_CERTIFICATE_ERROR"
            else: reason = "AUTH_FIREBASE_INVALID_TOKEN"
            self.last_verify_reason = reason
            log.warning("[Backend Auth] firebase_token_verified=false reason=%s exception=%s detail=%s", reason, name, detail)
            return None
        uid = str(decoded.get("uid") or "").strip()
        if not uid:
            self.last_verify_reason = "AUTH_FIREBASE_VERIFY_ERROR"
            log.warning("[Backend Auth] firebase_token_verified=false reason=AUTH_FIREBASE_VERIFY_ERROR exception=MissingUid")
            return None
        self.last_verify_reason = None
        self._remember(key, {**decoded, "uid": uid})
        log.info("[Backend Auth] firebase_token_verified=true uid_present=true")
        user = self.repo.ensure_firebase_user(uid, decoded.get("email") or "", decoded.get("name") or "", self.account_exists)
        return Identity(user) if user else None

    def account_exists(self, uid):
        """False only when Firebase says the account is gone; any other failure keeps the data."""
        try:
            self.auth.get_user(uid)
            return True
        except self.auth.UserNotFoundError:
            return False
        except Exception as exc:
            log.warning("[Backend Auth] account_lookup_failed exception=%s", type(exc).__name__)
            return True

    def delete_user(self, uid):
        try:
            self.auth.delete_user(uid)
        except self.auth.UserNotFoundError:
            pass
        # Cached tokens of the deleted user must stop authenticating (and recreating the row) at once.
        with self._verified_lock:
            self._verified = {k: v for k, v in self._verified.items() if v[1].get("uid") != uid}

    def revoke(self, token):
        # Firebase owns refresh-token revocation. Client logout signs out the
        # Firebase user; backend does not persist a second session token.
        return None

