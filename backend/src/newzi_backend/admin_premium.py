"""Premium given from the panel (painel.newzi.app): give, change, end and list courtesies.

The panel sends dates as days (``2026-11-01``) in the owner's time zone (ANALYTICS_TIMEZONE): Premium starts at the
beginning of the first day and lasts through the whole last day. The rules themselves live in subscriptions.py.
"""
from datetime import datetime, timedelta, timezone

from .admin import analytics_zone
from .subscriptions import GRANT_REASONS, add_grant, grant_status, revoke_grant, update_grant
from .timeutil import iso

MAX_EMAILS = 200


def _bounds(start_day, end_day):
    try:
        start = datetime.fromisoformat(str(start_day)).date()
        end = datetime.fromisoformat(str(end_day)).date()
    except ValueError:
        raise ValueError("dates must be YYYY-MM-DD") from None
    if end < start:
        raise ValueError("the end date must not come before the start date")
    zone = analytics_zone()
    begin = datetime(start.year, start.month, start.day, tzinfo=zone)
    finish = datetime(end.year, end.month, end.day, tzinfo=zone) + timedelta(days=1)
    return iso(begin), iso(finish)


def _emails(value):
    if isinstance(value, str):
        value = value.replace(";", ",").replace("\n", ",").split(",")
    emails = sorted({str(item).strip().casefold() for item in value or [] if str(item).strip()})
    if not emails:
        raise ValueError("inform at least one e-mail")
    if len(emails) > MAX_EMAILS:
        raise ValueError(f"at most {MAX_EMAILS} e-mails at a time")
    return emails


def give(repo, data, actor=None, now=None):
    """Give Premium to each e-mail with an account; returns who got it and which e-mails have no account."""
    now = now or datetime.now(timezone.utc)
    starts_at, ends_at = _bounds(data.get("start_day"), data.get("end_day"))
    if ends_at <= iso(now):
        raise ValueError("the end date is already past")
    reason = data.get("reason") or "cortesia"
    given, missing = [], []
    for email in _emails(data.get("emails")):
        user = repo.db.execute("SELECT id FROM users WHERE lower(email)=?", (email,)).fetchone()
        if not user:
            missing.append(email)
            continue
        grant_id = add_grant(repo, user["id"], starts_at, ends_at, reason, data.get("note"), actor, now)
        given.append({"email": email, "user_id": user["id"], "grant_id": grant_id})
    return {"given": given, "missing": missing, "starts_at": starts_at, "ends_at": ends_at}


def change(repo, grant_id, data, now=None):
    starts_at, ends_at = _bounds(data.get("start_day"), data.get("end_day"))
    if not update_grant(repo, grant_id, starts_at, ends_at, data.get("reason") or "cortesia", data.get("note"), now):
        raise LookupError("grant not found or already ended")
    return grant(repo, grant_id, now)


def end(repo, grant_id, actor=None, now=None):
    if not revoke_grant(repo, grant_id, actor, now):
        raise LookupError("grant not found or already ended")
    return grant(repo, grant_id, now)


def _public(row, now):
    out = dict(row)
    out["status"] = grant_status(row, now)
    return out


def grant(repo, grant_id, now=None):
    row = repo.db.execute("""SELECT g.*,u.email FROM premium_grants g LEFT JOIN users u ON u.id=g.user_id WHERE g.id=?""", (grant_id,)).fetchone()
    return _public(row, iso(now or datetime.now(timezone.utc))) if row else None


def grants(repo, user_id=None, now=None):
    stamp = iso(now or datetime.now(timezone.utc))
    where, params = ("WHERE g.user_id=?", (user_id,)) if user_id else ("", ())
    rows = repo.db.execute(f"""SELECT g.*,u.email FROM premium_grants g LEFT JOIN users u ON u.id=g.user_id {where}
        ORDER BY g.created_at DESC LIMIT 500""", params).fetchall()
    items = [_public(row, stamp) for row in rows]
    order = {"ativo": 0, "agendado": 1, "encerrado": 2, "retirado": 3}
    items.sort(key=lambda item: order[item["status"]])
    return {"grants": items, "reasons": list(GRANT_REASONS),
            "counts": {status: sum(item["status"] == status for item in items) for status in order}}
