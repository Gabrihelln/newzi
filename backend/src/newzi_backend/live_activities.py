"""Live Activities (iPhone, Premium): the score of a favourite team's game on the lock screen and Dynamic Island.

The app registers two kinds of APNs tokens (``live_activity_tokens``):

- ``start``: the phone's push-to-start token (iOS 17.2+). When a Premium fan's game is about to begin
  (football_alerts.py, at the kickoff reminder), the server starts the activity remotely, once per game and person.
- ``update``: the token of one running activity (any iOS 16.1+, also for activities the app started itself).
  Kickoff, goals and the final result update it; the final result ends it (it stays on screen a while).

Pushes go through FCM (firebase-admin 6.9+: ``APNSConfig.live_activity_token``) with the phone's FCM token, so no
separate APNs key is needed on the server. The JSON below must match ``MatchActivityAttributes`` in the iOS
widget extension (mobile/ios/NewziWidgets/MatchActivity.swift).
"""
import logging
import os
import time
import uuid

from .timeutil import iso, utc_now

log = logging.getLogger(__name__)
ATTRIBUTES_TYPE = "MatchActivityAttributes"
# How long the final score stays on the lock screen after the game ends.
END_DISMISS_SECONDS = int(os.getenv("LIVE_ACTIVITY_END_SECONDS", "3600"))
KINDS = ("start", "update")


def _bundle_id():
    return os.getenv("IOS_BUNDLE_ID", "app.newzi.ios")


def register_token(repo, uid, data):
    """``{"kind": "start"|"update", "token": <APNs hex>, "push_token": <FCM token>, "match_id": <id for update>}``."""
    from .subscriptions import require
    data = data or {}
    kind, token, fcm = data.get("kind"), str(data.get("token") or "").strip(), str(data.get("push_token") or "").strip()
    if kind not in KINDS:
        raise ValueError("kind must be start or update")
    if len(token) < 16 or len(fcm) < 10:
        raise ValueError("token and push_token are required")
    match_id = data.get("match_id")
    if kind == "update" and (isinstance(match_id, bool) or not isinstance(match_id, int)):
        raise ValueError("match_id is required for an activity token")
    require(repo, uid, "live_activities")
    now = iso(utc_now())
    if kind == "start":
        # One push-to-start token per phone (FCM token): a new one replaces the old.
        repo.db.execute("DELETE FROM live_activity_tokens WHERE user_id=? AND kind='start' AND fcm_token=? AND token<>?", (uid, fcm, token))
    repo.db.execute("""INSERT INTO live_activity_tokens(id,user_id,kind,token,fcm_token,match_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(token) DO UPDATE SET user_id=excluded.user_id,kind=excluded.kind,fcm_token=excluded.fcm_token,match_id=excluded.match_id,updated_at=excluded.updated_at""",
        ("live_" + uuid.uuid4().hex, uid, kind, token, fcm, match_id if kind == "update" else None, now, now))
    repo.db.commit()
    return {"status": "registered", "kind": kind}


def remove_token(repo, uid, token):
    repo.db.execute("DELETE FROM live_activity_tokens WHERE user_id=? AND token=?", (uid, token))
    repo.db.commit()
    return {"status": "removed"}


def _state(match, now):
    from .football import LIVE
    full = (match.get("score") or {}).get("fullTime") or {}
    status = match.get("status")
    return {"homeGoals": int(full.get("home") or 0), "awayGoals": int(full.get("away") or 0),
            "status": "LIVE" if status in LIVE else "FINISHED" if status == "FINISHED" else "SCHEDULED",
            "updatedAt": now.timestamp()}


def _attributes(match):
    from .football import COMPETITIONS, _kickoff, _team, _tla
    kickoff = _kickoff(match)
    code = (match.get("competition") or {}).get("code")
    return {"matchId": int(match["id"]), "home": _team(match.get("homeTeam")), "away": _team(match.get("awayTeam")),
            "homeTla": _tla(match.get("homeTeam")), "awayTla": _tla(match.get("awayTeam")),
            "competition": COMPETITIONS.get(code, (match.get("competition") or {}).get("name") or ""),
            "kickoff": kickoff.timestamp() if kickoff else time.time()}


def _wants(repo, uid):
    from .notifications import NotificationService
    settings = NotificationService(repo).settings(uid)
    return settings.get("notifications_enabled") and settings.get("live_activities_enabled")


def push_to_start(repo, match, users, now=None, sender=None):
    """Start the game's activity on the phones of these Premium fans (once per person and game)."""
    now = now or utc_now(); started = 0
    for uid in users:
        if not _wants(repo, uid):
            continue
        if repo.db.execute("SELECT 1 FROM live_activity_starts WHERE user_id=? AND match_id=?", (uid, match["id"])).fetchone():
            continue
        tokens = repo.db.execute("SELECT token,fcm_token FROM live_activity_tokens WHERE user_id=? AND kind='start'", (uid,)).fetchall()
        if not tokens:
            continue
        repo.db.execute("INSERT INTO live_activity_starts(user_id,match_id,created_at) VALUES(?,?,?) ON CONFLICT DO NOTHING", (uid, match["id"], iso(now)))
        repo.db.commit()
        attributes = _attributes(match)
        aps = {"timestamp": int(now.timestamp()), "event": "start", "content-state": _state(match, now),
               "attributes-type": ATTRIBUTES_TYPE, "attributes": attributes,
               "alert": {"title": f"{attributes['home']} x {attributes['away']}", "body": "Acompanhe o placar na tela de bloqueio."}}
        for row in tokens:
            started += _send(repo, row["fcm_token"], row["token"], aps, sender)
    return started


def push_match_update(repo, match, users, now=None, sender=None):
    """New score or status for every running activity of this game (ends it when the game is over)."""
    now = now or utc_now(); sent = 0
    state = _state(match, now)
    finished = state["status"] == "FINISHED"
    rows = repo.db.execute(f"""SELECT user_id,token,fcm_token FROM live_activity_tokens WHERE kind='update' AND match_id=?
        AND user_id IN ({','.join('?' for _ in users) or 'NULL'})""", (match["id"], *users)).fetchall()
    for row in rows:
        aps = {"timestamp": int(now.timestamp()), "event": "end" if finished else "update", "content-state": state}
        if finished:
            aps["dismissal-date"] = int(now.timestamp()) + END_DISMISS_SECONDS
        sent += _send(repo, row["fcm_token"], row["token"], aps, sender)
    if finished and rows:
        repo.db.execute("DELETE FROM live_activity_tokens WHERE kind='update' AND match_id=?", (match["id"],))
        repo.db.commit()
    return sent


def _send(repo, fcm_token, activity_token, aps, sender=None):
    sender = sender or _fcm_sender(repo)
    try:
        ok = sender(fcm_token, activity_token, aps)
    except Exception as exc:
        log.warning("live activity push failed: %s", exc)
        return 0
    if ok == "INVALID":
        repo.db.execute("DELETE FROM live_activity_tokens WHERE token=?", (activity_token,)); repo.db.commit()
        return 0
    return 1 if ok else 0


def _fcm_sender(repo):
    """FCM HTTP v1 with the activity's APNs token; the development provider only records what would be sent."""
    provider = getattr(getattr(repo, "config", None), "push_provider", os.getenv("PUSH_PROVIDER", "development"))
    if provider != "fcm":
        sent = _fcm_sender.development = getattr(_fcm_sender, "development", [])
        return lambda fcm, token, aps: sent.append({"fcm": fcm[-6:], "token": token[-6:], "aps": aps}) or True

    def send(fcm, token, aps):
        from .notifications import FCMPushProvider
        messaging = FCMPushProvider()._client()
        message = messaging.Message(token=fcm, apns=messaging.APNSConfig(
            live_activity_token=token,
            headers={"apns-push-type": "liveactivity", "apns-topic": _bundle_id() + ".push-type.liveactivity", "apns-priority": "10"},
            payload=messaging.APNSPayload(aps=messaging.Aps(custom_data=aps))))
        try:
            messaging.send(message)
            return True
        except (messaging.UnregisteredError, messaging.SenderIdMismatchError):
            return "INVALID"
    return send
