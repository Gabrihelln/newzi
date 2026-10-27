"""Announcements and promotions sent from the panel (painel.newzi.app), now or at a chosen time.

A campaign is stored in ``admin_push_campaigns``. When it is due (right away for "enviar agora", or in the worker's
notifications role for a scheduled one) its audience is resolved and one ``notification_jobs`` row is queued per
device, of kind ANNOUNCEMENT or PROMOTION; the worker delivers them like every other push, so the user's main
notification switch, invalid tokens and retries are handled the same way. The audience is resolved at send time,
so a campaign scheduled for next week reaches whoever matches then.

Taps open what ``target`` says, with the data keys app 1.0 already routes (notificationRouting.ts): ``screen``,
``story_id`` or an https ``url``.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

from .admin import local_day
from .subscriptions import WITH_ACCESS
from .timeutil import iso

KINDS = {"announcement": "ANNOUNCEMENT", "promotion": "PROMOTION"}
SCREENS = ("Subscription", "NotificationSettings", "ContentPreferences", "DailyBriefing", "Football", "History")
SEGMENTS = ("all", "premium_now", "not_premium", "never_premium", "ever_premium", "ex_premium")
PLATFORMS = ("ANDROID", "IOS")
MAX_TITLE, MAX_BODY = 65, 240
FINAL = ("SENT", "FAILED", "CANCELLED")


# ------------------------------------------------------------- validation
def _clean(data, now):
    kind = KINDS.get(str(data.get("kind") or ""))
    if not kind:
        raise ValueError("kind must be announcement or promotion")
    title, body = str(data.get("title") or "").strip(), str(data.get("body") or "").strip()
    if not title or not body:
        raise ValueError("title and body are required")
    if len(title) > MAX_TITLE or len(body) > MAX_BODY:
        raise ValueError(f"title up to {MAX_TITLE} characters and body up to {MAX_BODY}")
    target = _target(data.get("target") or {})
    audience = _audience(data.get("audience") or {})
    when = data.get("scheduled_for")
    if when:
        try:
            moment = datetime.fromisoformat(str(when).replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("scheduled_for must be an ISO date and time") from None
        if moment.tzinfo is None:
            raise ValueError("scheduled_for must carry its time zone")
        if moment < now - timedelta(minutes=1):
            raise ValueError("scheduled_for is in the past")
        when = iso(moment)
    return kind, title, body, target, audience, when


def _target(target):
    if not isinstance(target, dict):
        raise ValueError("target must be an object")
    image = str(target.get("image") or "").strip()
    if image and not image.startswith("https://"):
        raise ValueError("image must be an https address")
    clean = {"image": image} if image else {}
    screen, story, url = (str(target.get(key) or "").strip() for key in ("screen", "story_id", "url"))
    if screen:
        if screen not in SCREENS:
            raise ValueError("screen must be one of: " + ", ".join(SCREENS))
        clean["screen"] = screen
    elif story:
        clean["story_id"] = story[:120]
    elif url:
        if not url.startswith("https://"):
            raise ValueError("url must be an https address")
        clean["url"] = url[:500]
    return clean


def _audience(audience):
    if not isinstance(audience, dict):
        raise ValueError("audience must be an object")
    segment = audience.get("segment") or "all"
    if segment not in SEGMENTS:
        raise ValueError("segment must be one of: " + ", ".join(SEGMENTS))
    platform = str(audience.get("platform") or "").upper()
    if platform and platform not in PLATFORMS:
        raise ValueError("platform must be ANDROID or IOS")
    clean = {"segment": segment}
    if platform:
        clean["platform"] = platform
    for key in ("topic", "language"):
        if audience.get(key):
            clean[key] = str(audience[key]).strip()[:40]
    for key in ("team_id", "inactive_days"):
        if audience.get(key) not in (None, ""):
            try:
                clean[key] = max(0, int(audience[key]))
            except (TypeError, ValueError):
                raise ValueError(f"{key} must be a number") from None
    emails = audience.get("emails")
    if emails:
        if isinstance(emails, str):
            emails = emails.replace(";", ",").replace("\n", ",").split(",")
        clean["emails"] = sorted({str(item).strip().casefold() for item in emails if str(item).strip()})[:500]
    return clean


# ------------------------------------------------------------- audience
def _premium_sets(repo, now):
    stamp = iso(now)
    paid_now, paid_ever = set(), set()
    for row in repo.db.execute("SELECT user_id,status,expires_at FROM subscriptions").fetchall():
        paid_ever.add(row["user_id"])
        if row["status"] in WITH_ACCESS and (row["expires_at"] or "") > stamp:
            paid_now.add(row["user_id"])
    grant_now, grant_ever = set(), set()
    for row in repo.db.execute("SELECT user_id,starts_at,ends_at,revoked_at FROM premium_grants WHERE starts_at<=?", (stamp,)).fetchall():
        grant_ever.add(row["user_id"])
        if not row["revoked_at"] and row["ends_at"] > stamp:
            grant_now.add(row["user_id"])
    return paid_now | grant_now, paid_ever | grant_ever


def resolve_users(repo, audience, now=None):
    """The ids of the active accounts the audience describes."""
    now = now or datetime.now(timezone.utc)
    users = {row["id"]: row for row in repo.db.execute("SELECT id,email,language FROM users WHERE status='ACTIVE'").fetchall()}
    if audience.get("emails"):
        wanted = set(audience["emails"])
        return {uid for uid, row in users.items() if (row["email"] or "").casefold() in wanted}
    ids = set(users)
    segment = audience.get("segment", "all")
    if segment != "all":
        premium_now, premium_ever = _premium_sets(repo, now)
        ids &= {"premium_now": premium_now, "not_premium": ids - premium_now, "never_premium": ids - premium_ever,
                "ever_premium": premium_ever, "ex_premium": premium_ever - premium_now}[segment]
    if audience.get("language"):
        prefix = audience["language"].casefold()
        ids = {uid for uid in ids if (users[uid]["language"] or "").casefold().startswith(prefix)}
    if audience.get("topic"):
        topic = audience["topic"]
        following = set()
        for row in repo.db.execute("SELECT user_id,topics_json FROM user_preferences").fetchall():
            try:
                if topic in json.loads(row["topics_json"] or "[]"):
                    following.add(row["user_id"])
            except ValueError:
                pass
        ids &= following
    if audience.get("team_id") is not None:
        ids &= {row[0] for row in repo.db.execute("SELECT user_id FROM user_favorite_teams WHERE team_id=?", (audience["team_id"],))}
    if audience.get("inactive_days"):
        cutoff = (datetime.fromisoformat(local_day(now)) - timedelta(days=audience["inactive_days"])).date().isoformat()
        recent = {row[0] for row in repo.db.execute("SELECT DISTINCT user_id FROM user_activity_days WHERE day>?", (cutoff,))}
        ids -= recent
    return ids


def _devices(repo, ids, audience):
    if not ids:
        return []
    rows = repo.db.execute("SELECT id,user_id,platform FROM push_devices WHERE enabled=1 AND invalidated_at IS NULL").fetchall()
    platform = audience.get("platform")
    return [row for row in rows if row["user_id"] in ids and (not platform or row["platform"] == platform)]


def _main_switch_off(repo):
    return {row[0] for row in repo.db.execute("SELECT user_id FROM notification_settings WHERE notifications_enabled=0")}


def preview(repo, data, now=None):
    """How many people and phones a campaign would reach right now."""
    now = now or datetime.now(timezone.utc)
    audience = _audience(data.get("audience") or {})
    ids = resolve_users(repo, audience, now)
    devices = _devices(repo, ids - _main_switch_off(repo), audience)
    reached = {row["user_id"] for row in devices}
    return {"users": len(ids), "users_reachable": len(reached), "devices": len(devices),
            "by_platform": {name: sum(row["platform"] == name for row in devices) for name in PLATFORMS},
            "without_device": len(ids) - len(reached)}


# ------------------------------------------------------------- campaigns
def create(repo, data, now=None):
    """Store a campaign; one without ``scheduled_for`` is queued for delivery at once."""
    now = now or datetime.now(timezone.utc)
    kind, title, body, target, audience, when = _clean(data, now)
    campaign_id = "push_" + uuid.uuid4().hex
    stamp = iso(now)
    repo.db.execute("""INSERT INTO admin_push_campaigns(id,kind,title,body,target_json,audience_json,scheduled_for,status,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)""", (campaign_id, kind, title, body, json.dumps(target), json.dumps(audience),
                                         when or stamp, "SCHEDULED", stamp, stamp))
    repo.db.commit()
    if not when:
        dispatch(repo, campaign_id, now)
    return get(repo, campaign_id, now)


def update(repo, campaign_id, data, now=None):
    """Change a campaign that has not gone out yet (same fields as create)."""
    now = now or datetime.now(timezone.utc)
    kind, title, body, target, audience, when = _clean(data, now)
    changed = repo.db.execute("""UPDATE admin_push_campaigns SET kind=?,title=?,body=?,target_json=?,audience_json=?,scheduled_for=?,updated_at=?
        WHERE id=? AND status='SCHEDULED'""", (kind, title, body, json.dumps(target), json.dumps(audience), when or iso(now), iso(now), campaign_id)).rowcount
    repo.db.commit()
    if not changed:
        raise LookupError("only a scheduled campaign can be changed")
    if not when:
        dispatch(repo, campaign_id, now)
    return get(repo, campaign_id, now)


def cancel(repo, campaign_id, now=None):
    stamp = iso(now or datetime.now(timezone.utc))
    changed = repo.db.execute("UPDATE admin_push_campaigns SET status='CANCELLED',cancelled_at=?,updated_at=? WHERE id=? AND status='SCHEDULED'",
                              (stamp, stamp, campaign_id)).rowcount
    repo.db.commit()
    if not changed:
        raise LookupError("only a scheduled campaign can be cancelled")
    return get(repo, campaign_id, now)


def send_now(repo, campaign_id, now=None):
    now = now or datetime.now(timezone.utc)
    if not dispatch(repo, campaign_id, now):
        raise LookupError("only a scheduled campaign can be sent")
    return get(repo, campaign_id, now)


def dispatch(repo, campaign_id, now=None):
    """Queue one push per device of the campaign's audience; False when it is no longer scheduled."""
    now = now or datetime.now(timezone.utc)
    stamp = iso(now)
    # Claiming the row first means two workers (or a worker and the panel) never queue it twice.
    claimed = repo.db.execute("UPDATE admin_push_campaigns SET status='SENDING',dispatched_at=?,updated_at=? WHERE id=? AND status='SCHEDULED'",
                              (stamp, stamp, campaign_id)).rowcount
    repo.db.commit()
    if not claimed:
        return False
    campaign = repo.db.execute("SELECT * FROM admin_push_campaigns WHERE id=?", (campaign_id,)).fetchone()
    audience = json.loads(campaign["audience_json"] or "{}")
    ids = resolve_users(repo, audience, now)
    devices = _devices(repo, ids - _main_switch_off(repo), audience)
    data = {"type": campaign["kind"], "campaign_id": campaign_id, "delivery_id": campaign_id, **json.loads(campaign["target_json"] or "{}")}
    payload = json.dumps({"title": campaign["title"], "body": campaign["body"], "data": data}, ensure_ascii=False)
    for device in devices:
        repo.db.execute("""INSERT INTO notification_jobs(id,user_id,delivery_id,device_id,notification_type,scheduled_for,status,attempt_count,
            max_attempts,next_attempt_at,provider_message_id,last_error,created_at,updated_at,payload_json)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING""",
            ("notification_" + uuid.uuid4().hex, device["user_id"], campaign_id, device["id"], campaign["kind"], stamp, "PENDING", 0, 3,
             None, None, None, stamp, stamp, payload))
    repo.db.execute("UPDATE admin_push_campaigns SET users=?,devices=?,updated_at=? WHERE id=?",
                    (len({row["user_id"] for row in devices}), len(devices), stamp, campaign_id))
    repo.db.commit()
    return True


def dispatch_due(repo, now=None):
    """Worker: queue the scheduled campaigns whose time has come."""
    now = now or datetime.now(timezone.utc)
    due = [row["id"] for row in repo.db.execute("SELECT id FROM admin_push_campaigns WHERE status='SCHEDULED' AND scheduled_for<=?",
                                                (iso(now),)).fetchall()]
    return {"campaigns_dispatched": sum(1 for campaign_id in due if dispatch(repo, campaign_id, now))}


def _results(repo, campaign, now):
    """Delivery counts; frozen in the campaign once every push is final (old jobs are pruned after 30 days)."""
    if campaign["results_json"]:
        return json.loads(campaign["results_json"])
    counts = {row["status"]: row["n"] for row in repo.db.execute(
        "SELECT status,COUNT(*) AS n FROM notification_jobs WHERE delivery_id=? GROUP BY status", (campaign["id"],))}
    results = {"sent": counts.get("SENT", 0), "failed": counts.get("FAILED", 0), "cancelled": counts.get("CANCELLED", 0),
               "pending": counts.get("PENDING", 0) + counts.get("RUNNING", 0)}
    if campaign["status"] == "SENDING" and not results["pending"]:
        repo.db.execute("UPDATE admin_push_campaigns SET status='SENT',results_json=?,updated_at=? WHERE id=? AND status='SENDING'",
                        (json.dumps(results), iso(now), campaign["id"]))
        repo.db.commit()
    return results


def _public(repo, row, now):
    campaign = dict(row)
    results = _results(repo, row, now) if row["status"] in ("SENDING", "SENT") else None
    if results is not None and campaign["status"] == "SENDING" and not results["pending"]:
        campaign["status"] = "SENT"
    campaign.update(target=json.loads(campaign.pop("target_json") or "{}"), audience=json.loads(campaign.pop("audience_json") or "{}"),
                    results=results)
    campaign.pop("results_json", None)
    return campaign


def get(repo, campaign_id, now=None):
    row = repo.db.execute("SELECT * FROM admin_push_campaigns WHERE id=?", (campaign_id,)).fetchone()
    return _public(repo, row, now or datetime.now(timezone.utc)) if row else None


def campaigns(repo, limit=100, now=None):
    now = now or datetime.now(timezone.utc)
    rows = repo.db.execute("SELECT * FROM admin_push_campaigns ORDER BY scheduled_for DESC LIMIT ?", (max(1, min(int(limit), 500)),)).fetchall()
    return {"campaigns": [_public(repo, row, now) for row in rows], "screens": list(SCREENS), "segments": list(SEGMENTS),
            "topics": [dict(row) for row in repo.db.execute("SELECT code,name FROM topics WHERE active=1 ORDER BY name").fetchall()],
            "teams": [dict(row) for row in repo.db.execute("""SELECT t.id,t.name,COUNT(*) AS users FROM user_favorite_teams f
                JOIN football_teams t ON t.id=f.team_id GROUP BY t.id,t.name ORDER BY t.name""").fetchall()]}
