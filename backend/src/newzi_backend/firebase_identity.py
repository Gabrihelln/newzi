"""Firebase Admin identity boundary.

The Admin SDK is loaded only when Firebase authentication is enabled. Local
identity remains available for isolated legacy/unit tests until real Firebase
runtime validation is complete.
"""
from .identity import Identity, IdentityProvider
import logging

log = logging.getLogger("newzi.firebase_auth")


class FirebaseAdminIdentityProvider(IdentityProvider):
    def __init__(self, repo, project_id=""):
        self.repo = repo
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

    def authenticate(self, credentials):
        raise PermissionError("Firebase Authentication must be performed by the client")

    def resolve(self, token):
        if not token:
            self.last_verify_reason = "AUTH_EMPTY_TOKEN"
            return None
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
        log.info("[Backend Auth] firebase_token_verified=true uid_present=true")
        user = self.repo.ensure_firebase_user(uid, decoded.get("email") or "", decoded.get("name") or "")
        return Identity(user) if user else None

    def revoke(self, token):
        # Firebase owns refresh-token revocation. Client logout signs out the
        # Firebase user; backend does not persist a second session token.
        return None

