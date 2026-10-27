"""Read-only numbers for Analytics Newzi (painel.newzi.app), one function per panel screen.

Everything is computed from what the product database already stores, at request time: the volumes are small and
SQLite answers these in milliseconds. Days are local days in ANALYTICS_TIMEZONE (São Paulo by default), so "hoje"
on the panel is the owner's today. Timestamps are bucketed in Python because the SQL stays portable (no date
functions, see db.py).
"""
import json
import os
import shutil
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .admin import analytics_zone, local_day
from .subscriptions import WITH_ACCESS
from .timeutil import iso, parse

MAX_DAYS = 120


def _now(now=None):
    return now or datetime.now(timezone.utc)


def _days(days):
    try:
        return max(1, min(int(days), MAX_DAYS))
    except (TypeError, ValueError):
        return 30


def _day_list(days, now):
    today = datetime.fromisoformat(local_day(now)).date()
    return [(today - timedelta(days=offset)).isoformat() for offset in range(days - 1, -1, -1)]


def _start_of(day):
    """UTC instant when the local ``day`` (YYYY-MM-DD) begins."""
    return iso(datetime.fromisoformat(day).replace(tzinfo=analytics_zone()))


def _local(value):
    if not value:
        return None
    try:
        return local_day(parse(value))
    except (TypeError, ValueError):
        return None


def _series(days, values):
    """``[{"day", "value"}]`` for every day of the window, zero where nothing happened."""
    counts = Counter(values)
    return [{"day": day, "value": counts.get(day, 0)} for day in days]


def _all(repo, sql, params=()):
    return [dict(row) for row in repo.db.execute(sql, params).fetchall()]


def _one(repo, sql, params=()):
    row = repo.db.execute(sql, params).fetchone()
    return row[0] if row else None


def _active_users(repo, since_day, until_day=None):
    if until_day:
        return _one(repo, "SELECT COUNT(DISTINCT user_id) FROM user_activity_days WHERE day>=? AND day<=?", (since_day, until_day)) or 0
    return _one(repo, "SELECT COUNT(DISTINCT user_id) FROM user_activity_days WHERE day>=?", (since_day,)) or 0


def _plans(repo, now):
    """Accounts with Premium right now, split by where it came from."""
    rows = _all(repo, "SELECT user_id,store,period,status,expires_at FROM subscriptions WHERE expires_at>?", (iso(now),))
    active = [row for row in rows if row["status"] in WITH_ACCESS]
    paid = [row for row in active if row["store"] != "manual"]
    return {"premium": len(active), "paid": len(paid), "manual": len(active) - len(paid),
            "monthly": sum(row["period"] == "monthly" for row in paid), "annual": sum(row["period"] == "annual" for row in paid)}


# ------------------------------------------------------------- Visão geral
def overview(repo, days=30, now=None):
    now, days = _now(now), _days(days)
    window = _day_list(days, now)
    today = window[-1]
    since = _start_of(window[0])
    users_total = _one(repo, "SELECT COUNT(*) FROM users") or 0
    signups = [_local(row["created_at"]) for row in _all(repo, "SELECT created_at FROM users WHERE created_at>=?", (since,))]
    activity = _all(repo, "SELECT day,COUNT(*) AS users FROM user_activity_days WHERE day>=? GROUP BY day", (window[0],))
    by_day = {row["day"]: row["users"] for row in activity}
    deliveries = _all(repo, "SELECT local_date,status,audio_status FROM user_briefing_deliveries WHERE local_date>=?", (window[0],))
    listening = _all(repo, "SELECT p.completed_at,p.progress_seconds,p.duration_seconds FROM briefing_listening_progress p "
                           "JOIN user_briefing_deliveries d ON d.id=p.delivery_id WHERE d.local_date>=?", (window[0],))
    pushes = _all(repo, "SELECT status,COUNT(*) AS n FROM notification_jobs WHERE created_at>=? GROUP BY status", (since,))
    with_audio = sum(row["audio_status"] == "READY" for row in deliveries)
    week_start = (datetime.fromisoformat(today) - timedelta(days=6)).date().isoformat()
    month_start = (datetime.fromisoformat(today) - timedelta(days=29)).date().isoformat()
    return {
        "days": days,
        "since_activity": _one(repo, "SELECT MIN(day) FROM user_activity_days"),
        "users_total": users_total,
        "dau": by_day.get(today, 0), "wau": _active_users(repo, week_start), "mau": _active_users(repo, month_start),
        "signups": len([day for day in signups if day]),
        "plans": _plans(repo, now),
        "devices": _all(repo, "SELECT platform,COUNT(*) AS n FROM push_devices WHERE enabled=1 AND invalidated_at IS NULL GROUP BY platform"),
        "briefings": {"delivered": sum(row["status"] == "READY" for row in deliveries), "total": len(deliveries), "with_audio": with_audio,
                      "listened": len(listening), "completed": sum(1 for row in listening if row["completed_at"])},
        "pushes": {row["status"]: row["n"] for row in pushes},
        "series": {"active": [{"day": day, "value": by_day.get(day, 0)} for day in window], "signups": _series(window, signups)},
        "alerts": system_alerts(repo, now),
    }


# ------------------------------------------------------------- Usuários
def users(repo, query="", plan="", page=1, per_page=50, now=None):
    now = _now(now)
    page = max(1, int(page or 1))
    term = str(query or "").strip().casefold()[:120]
    where, params = "", []
    if term:
        where = "WHERE lower(u.email) LIKE ? OR lower(u.display_name) LIKE ? OR u.id=?"
        params = [f"%{term}%", f"%{term}%", term]
    rows = _all(repo, f"""SELECT u.id,u.email,u.display_name,u.created_at,u.status,u.onboarding_status,
            (SELECT MAX(day) FROM user_activity_days a WHERE a.user_id=u.id) AS last_active,
            (SELECT COUNT(*) FROM user_activity_days a WHERE a.user_id=u.id) AS active_days
        FROM users u {where} ORDER BY u.created_at DESC""", params)
    subs = {row["user_id"]: row for row in _all(repo, "SELECT user_id,store,status,expires_at FROM subscriptions")}
    devices = {}
    for row in _all(repo, "SELECT user_id,platform,app_version FROM push_devices WHERE invalidated_at IS NULL ORDER BY last_seen_at DESC"):
        devices.setdefault(row["user_id"], row)
    stamp = iso(now)
    for row in rows:
        sub = subs.get(row["id"])
        premium = bool(sub) and sub["status"] in WITH_ACCESS and (sub["expires_at"] or "") > stamp
        row["plan"] = ("premium_manual" if sub["store"] == "manual" else "premium") if premium else "basic"
        device = devices.get(row["id"])
        row["platform"], row["app_version"] = (device["platform"], device["app_version"]) if device else (None, None)
    if plan in ("basic", "premium", "premium_manual"):
        rows = [row for row in rows if row["plan"] == plan]
    start = (page - 1) * per_page
    return {"total": len(rows), "page": page, "per_page": per_page, "users": rows[start:start + per_page]}


def user_detail(repo, uid, now=None):
    now = _now(now)
    user = repo.get_user(uid)
    if not user:
        return None
    from .subscriptions import subscription_for
    plan = subscription_for(repo, uid, now)
    sub = repo.db.execute("SELECT * FROM subscriptions WHERE user_id=?", (uid,)).fetchone()
    deliveries = _all(repo, """SELECT d.id,d.local_date,d.slot,d.kind,d.theme,d.status,d.audio_status,d.delivery_time,d.delivered_at,
            d.selected_voice_id,d.generation_error_code,p.progress_seconds,p.duration_seconds,p.completed_at
        FROM user_briefing_deliveries d LEFT JOIN briefing_listening_progress p ON p.delivery_id=d.id AND p.user_id=d.user_id
        WHERE d.user_id=? ORDER BY d.local_date DESC,d.slot DESC LIMIT 30""", (uid,))
    count = lambda table: _one(repo, f"SELECT COUNT(*) FROM {table} WHERE user_id=?", (uid,)) or 0
    return {
        "user": repo.public_user(user),
        "preferences": repo.get_preferences(uid),
        "briefing_slots": _all(repo, "SELECT slot,delivery_time,theme,length,enabled FROM briefing_slots WHERE user_id=? ORDER BY slot", (uid,)),
        "plan": {"tier": plan["tier"], "period": plan["period"], "status": plan["status"], "expires_at": plan["expires_at"],
                 "will_renew": plan["will_renew"], "store": sub["store"] if sub else None, "started_at": sub["started_at"] if sub else None},
        "devices": _all(repo, """SELECT platform,app_version,locale,timezone,enabled,created_at,last_seen_at,invalidated_at
            FROM push_devices WHERE user_id=? ORDER BY last_seen_at DESC""", (uid,)),
        "notification_settings": dict(repo.db.execute("SELECT * FROM notification_settings WHERE user_id=?", (uid,)).fetchone() or {}),
        "activity": [row["day"] for row in _all(repo, "SELECT day FROM user_activity_days WHERE user_id=? ORDER BY day DESC LIMIT 60", (uid,))],
        "deliveries": deliveries,
        "notifications": _all(repo, """SELECT notification_type,status,scheduled_for,last_error,updated_at FROM notification_jobs
            WHERE user_id=? ORDER BY scheduled_for DESC LIMIT 30""", (uid,)),
        "counts": {"saved_stories": count("saved_stories"), "saved_briefings": count("saved_briefings"), "collections": count("saved_collections"),
                   "keyword_alerts": count("keyword_alerts"), "followed_stories": count("followed_stories"),
                   "favorite_teams": count("user_favorite_teams"), "feedback": count("article_feedback")},
        "keyword_alerts": [row["keyword"] for row in _all(repo, "SELECT keyword FROM keyword_alerts WHERE user_id=? ORDER BY created_at", (uid,))],
        "favorite_teams": [row["name"] for row in _all(repo, """SELECT t.name FROM user_favorite_teams f JOIN football_teams t ON t.id=f.team_id
            WHERE f.user_id=? ORDER BY f.position""", (uid,))],
    }


# ------------------------------------------------------------- Retenção
def retention(repo, weeks=8, now=None):
    """Weekly sign-up cohorts: of the people who joined in a week, how many were active 1, 7 and 30 days later."""
    now = _now(now)
    weeks = max(1, min(int(weeks or 8), 26))
    today = datetime.fromisoformat(local_day(now)).date()
    since = today - timedelta(days=7 * weeks)
    joined = {row["id"]: _local(row["created_at"]) for row in _all(repo, "SELECT id,created_at FROM users WHERE created_at>=?", (_start_of(since.isoformat()),))}
    active = {}
    for row in _all(repo, "SELECT user_id,day FROM user_activity_days WHERE day>=?", (since.isoformat(),)):
        active.setdefault(row["user_id"], set()).add(row["day"])
    cohorts = {}
    for uid, day in joined.items():
        if not day:
            continue
        start = datetime.fromisoformat(day).date()
        week = (start - timedelta(days=start.weekday())).isoformat()
        cohort = cohorts.setdefault(week, {"week": week, "users": 0, "d1": 0, "d7": 0, "d30": 0, "d1_due": 0, "d7_due": 0, "d30_due": 0})
        cohort["users"] += 1
        seen = active.get(uid, set())
        for name, offset in (("d1", 1), ("d7", 7), ("d30", 30)):
            target = start + timedelta(days=offset)
            if target > today:
                continue
            cohort[name + "_due"] += 1
            # Active on the day itself or within the two following days counts as having come back.
            if any((target + timedelta(days=extra)).isoformat() in seen for extra in range(3)):
                cohort[name] += 1
    at_risk = _all(repo, """SELECT u.id,u.email,MAX(a.day) AS last_active FROM users u JOIN user_activity_days a ON a.user_id=u.id
        GROUP BY u.id,u.email HAVING MAX(a.day)<? ORDER BY MAX(a.day) DESC LIMIT 50""", ((today - timedelta(days=7)).isoformat(),))
    return {"cohorts": sorted(cohorts.values(), key=lambda row: row["week"], reverse=True), "at_risk": at_risk,
            "since_activity": _one(repo, "SELECT MIN(day) FROM user_activity_days")}


# ------------------------------------------------------------- Briefing e áudio
def briefings(repo, days=14, now=None):
    now, days = _now(now), _days(days)
    window = _day_list(days, now)
    rows = _all(repo, """SELECT d.local_date,d.kind,d.status,d.audio_status,d.selected_voice_id,d.generation_error_code,d.voice_fallback_reason,
            p.completed_at,p.progress_seconds,p.duration_seconds
        FROM user_briefing_deliveries d LEFT JOIN briefing_listening_progress p ON p.delivery_id=d.id AND p.user_id=d.user_id
        WHERE d.local_date>=?""", (window[0],))
    per_day = {day: {"day": day, "total": 0, "ready": 0, "audio_ready": 0, "audio_failed": 0, "listened": 0, "completed": 0} for day in window}
    for row in rows:
        bucket = per_day.get(row["local_date"])
        if not bucket:
            continue
        bucket["total"] += 1
        bucket["ready"] += row["status"] == "READY"
        bucket["audio_ready"] += row["audio_status"] == "READY"
        bucket["audio_failed"] += row["audio_status"] == "FAILED"
        bucket["listened"] += row["progress_seconds"] is not None and row["progress_seconds"] > 0
        bucket["completed"] += bool(row["completed_at"])
    stops = Counter()
    for row in rows:
        if row["progress_seconds"] and row["duration_seconds"] and not row["completed_at"]:
            stops[min(9, int(10 * row["progress_seconds"] / row["duration_seconds"]))] += 1
    since = _start_of(window[0])
    audio_jobs = _all(repo, "SELECT status,COUNT(*) AS n FROM audio_generation_jobs WHERE created_at>=? GROUP BY status", (since,))
    generation = _all(repo, "SELECT status,COUNT(*) AS n FROM generation_jobs WHERE briefing_date>=? GROUP BY status", (window[0],))
    phases = _all(repo, "SELECT phase,AVG(duration_ms) AS avg_ms,COUNT(*) AS n FROM audio_job_phases WHERE started_at>=? GROUP BY phase", (since,))
    return {
        "days": days,
        "per_day": list(per_day.values()),
        "kinds": dict(Counter(row["kind"] for row in rows)),
        "voices": dict(Counter(row["selected_voice_id"] or "—" for row in rows)),
        "errors": Counter(row["generation_error_code"] for row in rows if row["generation_error_code"]).most_common(10),
        "voice_fallbacks": Counter(row["voice_fallback_reason"] for row in rows if row["voice_fallback_reason"]).most_common(10),
        "stop_points": [{"decile": index * 10, "n": stops.get(index, 0)} for index in range(10)],
        "generation_jobs": {row["status"]: row["n"] for row in generation},
        "audio_jobs": {row["status"]: row["n"] for row in audio_jobs},
        "audio_phases": phases,
        "on_demand": _all(repo, "SELECT status,COUNT(*) AS n FROM manual_refresh_requests WHERE requested_at>=? GROUP BY status", (since,)),
    }


# ------------------------------------------------------------- Conteúdo
def content(repo, days=14, now=None, health=None):
    now, days = _now(now), _days(days)
    window = _day_list(days, now)
    since = _start_of(window[0])
    indexed = [_local(row["indexed_at"]) for row in _all(repo, "SELECT indexed_at FROM indexed_content WHERE indexed_at>=?", (since,))]
    runs = _all(repo, """SELECT status,started_at,completed_at,sources_attempted,sources_successful,articles_new,articles_updated
        FROM content_ingestion_runs ORDER BY started_at DESC LIMIT 20""")
    if health is None:
        try:
            from .source_health import source_health_report
            health = source_health_report(repo, now)
        except Exception as exc:          # the engine's store may be unreachable; the rest of the screen still answers
            health = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    sources = health.get("sources", []) if isinstance(health, dict) else health
    topics = Counter()
    for row in _all(repo, "SELECT topics_json FROM user_preferences"):
        try:
            topics.update(json.loads(row["topics_json"] or "[]"))
        except ValueError:
            pass
    names = {row["code"]: row["name"] for row in _all(repo, "SELECT code,name FROM topics")}
    ratings = _all(repo, "SELECT rating,COUNT(*) AS n FROM article_feedback GROUP BY rating ORDER BY rating")
    return {
        "days": days,
        "indexed_per_day": _series(window, indexed),
        "articles_total": _one(repo, "SELECT COUNT(*) FROM indexed_content") or 0,
        "runs": runs,
        "sources": {"by_status": dict(Counter(source.get("status") for source in sources)),
                    "attention": [source for source in sources if source.get("status") not in ("OK", "DISABLED")][:60],
                    "error": health.get("error") if isinstance(health, dict) else None},
        "topics_followed": [{"code": code, "name": names.get(code, code), "users": n} for code, n in topics.most_common(30)],
        "ratings": ratings,
    }


# ------------------------------------------------------------- Notificações
def notifications(repo, days=14, now=None):
    now, days = _now(now), _days(days)
    window = _day_list(days, now)
    since = _start_of(window[0])
    jobs = _all(repo, "SELECT notification_type,status,COUNT(*) AS n FROM notification_jobs WHERE created_at>=? GROUP BY notification_type,status", (since,))
    by_type = {}
    for row in jobs:
        by_type.setdefault(row["notification_type"], {})[row["status"]] = row["n"]
    sent = [_local(row["updated_at"]) for row in _all(repo, "SELECT updated_at FROM notification_jobs WHERE status='SENT' AND created_at>=?", (since,))]
    settings_columns = [name for name in repo.db.table_columns("notification_settings") if name.endswith("_enabled")]
    settings = {}
    if settings_columns:
        row = repo.db.execute("SELECT COUNT(*) AS total," + ",".join(f"SUM({name}) AS {name}" for name in settings_columns)
                              + " FROM notification_settings").fetchone()
        settings = dict(row) if row else {}
    return {
        "days": days,
        "devices": _all(repo, """SELECT platform,SUM(CASE WHEN enabled=1 AND invalidated_at IS NULL THEN 1 ELSE 0 END) AS active,
            SUM(CASE WHEN invalidated_at IS NOT NULL THEN 1 ELSE 0 END) AS invalidated,COUNT(*) AS total FROM push_devices GROUP BY platform"""),
        "settings": settings,
        "by_type": by_type,
        "sent_per_day": _series(window, sent),
        "errors": _all(repo, """SELECT last_error,COUNT(*) AS n FROM notification_jobs WHERE status='FAILED' AND created_at>=?
            GROUP BY last_error ORDER BY COUNT(*) DESC LIMIT 10""", (since,)),
    }


# ------------------------------------------------------------- Assinaturas
def subscriptions(repo, days=90, now=None):
    now, days = _now(now), _days(days)
    window = _day_list(days, now)
    rows = _all(repo, """SELECT s.user_id,u.email,s.period,s.status,s.store,s.product_id,s.started_at,s.expires_at,s.auto_renew,s.updated_at
        FROM subscriptions s LEFT JOIN users u ON u.id=s.user_id ORDER BY s.updated_at DESC""")
    stamp = iso(now)
    for row in rows:
        row["active"] = row["status"] in WITH_ACCESS and (row["expires_at"] or "") > stamp
    paid = [row for row in rows if row["store"] != "manual"]
    return {
        "days": days,
        "plans": _plans(repo, now),
        "by_status": dict(Counter(row["status"] for row in paid)),
        "by_store": dict(Counter(row["store"] for row in paid if row["active"])),
        "renewal_off": sum(1 for row in paid if row["active"] and not row["auto_renew"]),
        "started_per_day": _series(window, [_local(row["started_at"]) for row in paid if row["started_at"]]),
        "conversion": {"users": _one(repo, "SELECT COUNT(*) FROM users") or 0, "paid": _plans(repo, now)["paid"]},
        "subscriptions": rows[:200],
        "billing": {"enabled": os.getenv("BILLING_ENABLED", "").lower() in ("1", "true", "yes"),
                    "enforced": os.getenv("PREMIUM_ENFORCED", "").lower() in ("1", "true", "yes")},
    }


# ------------------------------------------------------------- Esportes
def football(repo, days=30, now=None):
    now, days = _now(now), _days(days)
    since = _start_of(_day_list(days, now)[0])
    return {
        "days": days,
        "users_with_teams": _one(repo, "SELECT COUNT(DISTINCT user_id) FROM user_favorite_teams") or 0,
        "teams": _all(repo, """SELECT t.name,COUNT(*) AS users FROM user_favorite_teams f JOIN football_teams t ON t.id=f.team_id
            GROUP BY t.name ORDER BY COUNT(*) DESC LIMIT 30"""),
        "followed_matches": _one(repo, "SELECT COUNT(*) FROM user_followed_matches WHERE created_at>=?", (since,)) or 0,
        "match_audio": _all(repo, "SELECT status,COUNT(*) AS n FROM football_match_audio WHERE created_at>=? GROUP BY status", (since,)),
        "live_activities": _one(repo, "SELECT COUNT(*) FROM live_activity_starts WHERE created_at>=?", (since,)) or 0,
        "team_pushes": _all(repo, """SELECT notification_type,status,COUNT(*) AS n FROM notification_jobs
            WHERE created_at>=? AND notification_type LIKE 'TEAM%' GROUP BY notification_type,status""", (since,)),
    }


# ------------------------------------------------------------- Sistema
def _disk(path):
    try:
        usage = shutil.disk_usage(path)
        return {"path": str(path), "total": usage.total, "used": usage.used, "free": usage.free,
                "percent": round(100 * usage.used / usage.total, 1) if usage.total else None}
    except OSError:
        return None


def _latest_backup():
    folder = Path(os.getenv("NEWZI_BACKUP_DIR", "/var/lib/newzi-backup/copies"))
    try:
        copies = sorted(folder.glob("product_backend-*.sqlite3.gz"))
    except OSError:
        return None
    if not copies:
        return {"folder": str(folder), "latest": None, "count": 0}
    latest = copies[-1]
    try:
        stat = latest.stat()
    except OSError:
        return None
    return {"folder": str(folder), "latest": latest.name, "count": len(copies), "size": stat.st_size,
            "at": iso(datetime.fromtimestamp(stat.st_mtime, timezone.utc))}


def _queues(repo):
    one = lambda sql: _one(repo, sql) or 0
    return {"generation": one("SELECT COUNT(*) FROM generation_jobs WHERE status IN ('PENDING','RUNNING')"),
            "audio": one("SELECT COUNT(*) FROM audio_generation_jobs WHERE status IN ('PENDING','RUNNING')"),
            "notifications": one("SELECT COUNT(*) FROM notification_jobs WHERE status IN ('PENDING','RUNNING')"),
            "on_demand": one("SELECT COUNT(*) FROM manual_refresh_requests WHERE status NOT IN ('READY','FAILED')")}


def system(repo, now=None):
    now = _now(now)
    database = Path(repo.path) if repo.dialect == "sqlite" else None
    return {
        "now": iso(now),
        "workers": _all(repo, "SELECT worker_id,roles,started_at,last_cycle_at,last_success_at,last_error,cycle_ms,cycles FROM worker_heartbeats ORDER BY last_cycle_at DESC"),
        "queues": _queues(repo),
        "last_ingestion": dict(repo.db.execute("SELECT status,started_at,completed_at,articles_new FROM content_ingestion_runs "
                                               "ORDER BY started_at DESC LIMIT 1").fetchone() or {}),
        "database": {"dialect": repo.dialect, "size": database.stat().st_size if database and database.exists() else None,
                     "migrations": [row["id"] for row in _all(repo, "SELECT id FROM schema_versions ORDER BY id DESC LIMIT 3")]},
        "disk": _disk(database.parent if database else "/"),
        "backup": _latest_backup(),
        "logins": _all(repo, "SELECT client,ok,created_at FROM admin_actions WHERE action='login' ORDER BY id DESC LIMIT 15"),
        "settings": {name: os.getenv(name) for name in ("APP_ENV", "PUSH_PROVIDER", "TTS_PROVIDER", "BILLING_ENABLED", "PREMIUM_ENFORCED",
                                                       "NOTIFICATIONS_ENABLED", "BRIEFING_GENERATOR")},
    }


def system_alerts(repo, now=None):
    """What needs a look today (shown on top of Visão geral)."""
    now = _now(now)
    alerts = []
    stale = iso(now - timedelta(seconds=int(os.getenv("WORKER_STALE_SECONDS", "300"))))
    workers = _all(repo, "SELECT worker_id,last_cycle_at,last_error FROM worker_heartbeats")
    if not workers:
        alerts.append({"level": "error", "text": "Nenhum worker registrou atividade nas últimas 24 h."})
    for worker in workers:
        if worker["last_cycle_at"] < stale:
            alerts.append({"level": "error", "text": f"Worker {worker['worker_id']} parado desde {worker['last_cycle_at']}."})
        elif worker["last_error"]:
            alerts.append({"level": "warn", "text": f"Último ciclo do worker {worker['worker_id']} terminou com erro."})
    last = _one(repo, "SELECT MAX(started_at) FROM content_ingestion_runs WHERE status<>'RUNNING'")
    if last and last < iso(now - timedelta(hours=1)):
        alerts.append({"level": "warn", "text": f"Última coleta de notícias em {last}."})
    today = local_day(now)
    failed = _one(repo, "SELECT COUNT(*) FROM user_briefing_deliveries WHERE local_date=? AND audio_status='FAILED'", (today,)) or 0
    if failed:
        alerts.append({"level": "warn", "text": f"{failed} áudio(s) de briefing falharam hoje."})
    queues = _queues(repo)
    if queues["audio"] > 20:
        alerts.append({"level": "warn", "text": f"Fila de áudio com {queues['audio']} itens."})
    backup = _latest_backup()
    if backup and backup.get("at") and backup["at"] < iso(now - timedelta(hours=30)):
        alerts.append({"level": "warn", "text": f"Último backup em {backup['at']}."})
    database = Path(repo.path) if repo.dialect == "sqlite" else None
    disk = _disk(database.parent if database else "/")
    if disk and disk["percent"] and disk["percent"] > 80:
        alerts.append({"level": "error", "text": f"Disco da VPS em {disk['percent']}%."})
    return alerts
