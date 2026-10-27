"""Analytics Newzi (painel.newzi.app): the panel's own sign-in, its action log, and the days each user used the app.

The panel has one account, set in the environment, with a password of its own (not an app account):

    ADMIN_EMAIL=owner@example.com
    ADMIN_PASSWORD_HASH=scrypt:...      generated on the server with backend/admin_password.py
    ADMIN_HOST=painel.newzi.app         optional: the panel's routes answer 404 on any other host

Without ADMIN_EMAIL and ADMIN_PASSWORD_HASH the panel's routes answer 404. A sign-in opens a 12-hour session kept in
``admin_sessions`` (only its hash is stored), which ends when the password changes; five wrong passwords in a row lock the sign-in for 15 minutes. Every
sign-in, right or wrong, is written to ``admin_actions``.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .timeutil import iso

SESSION_HOURS = 12
MAX_FAILURES = 5
LOCK_MINUTES = 15
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **SCRYPT)
    # ':' separated: no '$', which a shell sourcing the env file would expand.
    return "scrypt:{n}:{r}:{p}:{salt}:{digest}".format(**SCRYPT, salt=base64.b64encode(salt).decode(),
                                                       digest=base64.b64encode(digest).decode())


def verify_password(password, stored):
    try:
        scheme, n, r, p, salt, digest = (stored or "").split(":")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def configured():
    return bool(admin_email() and _password_hash())


def _password_hash():
    return os.getenv("ADMIN_PASSWORD_HASH", "").strip()


def _password_tag():
    """Ties a session to the password it was opened with: a new password ends every open session."""
    return hashlib.sha256(_password_hash().encode()).hexdigest()[:16]


def admin_email():
    return os.getenv("ADMIN_EMAIL", "").strip().casefold()


def allowed_host(host):
    expected = os.getenv("ADMIN_HOST", "").strip().casefold()
    return not expected or (host or "").split(":")[0].casefold() == expected


def record(repo, action, *, actor=None, client=None, ok=True, detail=None, now=None):
    repo.db.execute("INSERT INTO admin_actions(action,actor,client,detail_json,ok,created_at) VALUES(?,?,?,?,?,?)",
                    (action, actor, client, json.dumps(detail or {}, ensure_ascii=False), 1 if ok else 0,
                     iso(now or datetime.now(timezone.utc))))
    repo.db.commit()


def locked_until(repo, now=None):
    """When the sign-in opens again after MAX_FAILURES wrong passwords in a row, or None."""
    now = now or datetime.now(timezone.utc)
    rows = repo.db.execute("SELECT ok,created_at FROM admin_actions WHERE action='login' ORDER BY id DESC LIMIT ?",
                           (MAX_FAILURES,)).fetchall()
    if len(rows) < MAX_FAILURES or any(row["ok"] for row in rows):
        return None
    until = datetime.fromisoformat(rows[0]["created_at"].replace("Z", "+00:00")) + timedelta(minutes=LOCK_MINUTES)
    return until if until > now else None


def login(repo, email, password, client=None, now=None):
    """A session token for the right e-mail and password; raises PermissionError otherwise.

    Raises LookupError(until) while the sign-in is locked."""
    now = now or datetime.now(timezone.utc)
    until = locked_until(repo, now)
    if until:
        raise LookupError(until)
    email = str(email or "").strip().casefold()[:254]
    # Both checks always run, so a wrong e-mail takes as long as a wrong password.
    right_email = hmac.compare_digest(email.encode(), admin_email().encode())
    right_password = verify_password(str(password or ""), _password_hash())
    ok = configured() and right_email and right_password
    record(repo, "login", actor=email or None, client=client, ok=ok, now=now)
    if not ok:
        raise PermissionError("invalid credentials")
    token = secrets.token_urlsafe(32)
    repo.db.execute("DELETE FROM admin_sessions WHERE expires_at<?", (iso(now),))
    repo.db.execute("INSERT INTO admin_sessions(token_hash,password_tag,created_at,expires_at) VALUES(?,?,?,?)",
                    (_digest(token), _password_tag(), iso(now), iso(now + timedelta(hours=SESSION_HOURS))))
    repo.db.commit()
    return token


def session_valid(repo, token, now=None):
    if not token or not configured():
        return False
    row = repo.db.execute("SELECT password_tag,expires_at FROM admin_sessions WHERE token_hash=?", (_digest(token),)).fetchone()
    return bool(row) and row["password_tag"] == _password_tag() and row["expires_at"] > iso(now or datetime.now(timezone.utc))


def logout(repo, token):
    if token:
        repo.db.execute("DELETE FROM admin_sessions WHERE token_hash=?", (_digest(token),))
        repo.db.commit()


def _digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


# ------------------------------------------------------------- daily activity
def analytics_zone():
    return ZoneInfo(os.getenv("ANALYTICS_TIMEZONE", "America/Sao_Paulo"))


def local_day(moment=None):
    return (moment or datetime.now(timezone.utc)).astimezone(analytics_zone()).date().isoformat()


_seen = {"day": None, "users": set()}


def already_recorded(uid, now=None):
    return _seen["day"] == local_day(now) and uid in _seen["users"]


def record_activity(repo, uid, now=None):
    """Mark ``uid`` as active today: one row per user per day, and one write per user per day from this process."""
    now = now or datetime.now(timezone.utc)
    day = local_day(now)
    if already_recorded(uid, now):
        return
    repo.db.execute("INSERT INTO user_activity_days(user_id,day,first_seen_at) VALUES(?,?,?) ON CONFLICT(user_id,day) DO NOTHING",
                    (uid, day, iso(now)))
    repo.db.commit()
    if _seen["day"] != day:
        _seen.update(day=day, users=set())
    _seen["users"].add(uid)
