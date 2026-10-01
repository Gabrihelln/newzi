"""Local identity provider abstraction for Phase 4.3."""
import hashlib, hmac, secrets, time
from datetime import datetime, timedelta, timezone


class Identity:
    def __init__(self, user): self.user_id=user["id"]; self.email=user["email"]; self.status=user["status"]


class IdentityProvider:
    def authenticate(self, credentials): raise NotImplementedError
    def resolve(self, token): raise NotImplementedError
    def revoke(self, token): raise NotImplementedError


class LocalIdentityProvider(IdentityProvider):
    def __init__(self, repo, ttl_hours=24): self.repo=repo; self.ttl_hours=ttl_hours
    @staticmethod
    def normalize_email(email): return str(email or "").strip().casefold()
    @staticmethod
    def hash_password(password):
        if not isinstance(password,str) or len(password)<8: raise ValueError("password must contain at least 8 characters")
        salt=secrets.token_bytes(16); digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,310000); return "pbkdf2_sha256$310000$"+salt.hex()+"$"+digest.hex()
    @staticmethod
    def verify_password(password, encoded):
        try:
            algorithm, rounds, salt_hex, digest_hex=encoded.split("$",3); actual=hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt_hex),int(rounds)); return hmac.compare_digest(actual.hex(),digest_hex)
        except Exception: return False
    def _issue(self,user):
        raw=secrets.token_urlsafe(32); token_hash=hashlib.sha256(raw.encode()).hexdigest(); created=datetime.now(timezone.utc); expires=created+timedelta(hours=self.ttl_hours); self.repo.db.execute("INSERT INTO auth_sessions(token_hash,user_id,created_at,expires_at,revoked_at) VALUES(?,?,?,?,NULL)",(token_hash,user["id"],created.isoformat(),expires.isoformat())); self.repo.db.commit(); return raw,expires.isoformat()
    def register(self,email,password,display_name):
        email=self.normalize_email(email)
        if not email or "@" not in email: raise ValueError("valid email is required")
        if not display_name or len(display_name.strip())<1: raise ValueError("display_name is required")
        if self.repo.db.execute("SELECT id FROM users WHERE lower(email)=?",(email,)).fetchone(): raise ValueError("email already registered")
        uid="user_"+secrets.token_hex(12); t=datetime.now(timezone.utc).isoformat(); password_hash=self.hash_password(password); self.repo.db.execute("INSERT INTO users(id,email,display_name,language,timezone,created_at,updated_at,status,password_hash,onboarding_status) VALUES(?,?,?,?,?,?,?,?,?,?)",(uid,email,display_name.strip(),self.repo.config.default_language,self.repo.config.default_timezone,t,t,"ACTIVE",password_hash,"NOT_STARTED")); self.repo.db.commit(); self.repo.save_preferences(uid,{})
        user=self.repo.get_user(uid); token,expires=self._issue(user); return Identity(user),token,expires
    def authenticate(self,credentials):
        email=self.normalize_email(credentials.get("email")); user=self.repo.db.execute("SELECT * FROM users WHERE lower(email)=?",(email,)).fetchone()
        if not user or user["status"]!="ACTIVE" or not user["password_hash"] or not self.verify_password(credentials.get("password", ""),user["password_hash"]): raise PermissionError("invalid credentials")
        user=dict(user); token,expires=self._issue(user); return Identity(user),token,expires
    def resolve(self,token):
        if not token: return None
        token_hash=hashlib.sha256(token.encode()).hexdigest(); row=self.repo.db.execute("SELECT s.*,u.status FROM auth_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?",(token_hash,)).fetchone()
        if not row or row["revoked_at"] or row["status"]!="ACTIVE": return None
        if datetime.fromisoformat(row["expires_at"])<=datetime.now(timezone.utc): return None
        user=self.repo.get_user(row["user_id"]); return Identity(user) if user else None
    def revoke(self,token):
        token_hash=hashlib.sha256((token or "").encode()).hexdigest(); self.repo.db.execute("UPDATE auth_sessions SET revoked_at=? WHERE token_hash=?",(datetime.now(timezone.utc).isoformat(),token_hash)); self.repo.db.commit()


class LocalAuthRateLimiter:
    def __init__(self, limit=10, window_seconds=60): self.limit=limit; self.window=window_seconds; self.hits={}
    def allow(self,key):
        now=time.time(); values=[x for x in self.hits.get(key,[]) if now-x<self.window]; allowed=len(values)<self.limit
        if allowed: values.append(now)
        self.hits[key]=values; return allowed

