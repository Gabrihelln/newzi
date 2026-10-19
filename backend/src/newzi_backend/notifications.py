"""Phase 4.7 push delivery foundation with provider and device boundaries."""
import json, os, time, uuid
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from zoneinfo import ZoneInfo


from .timeutil import iso, now_iso, parse


@dataclass(frozen=True)
class PushResult:
    success: bool
    provider_message_id: str | None = None
    failure_reason: str | None = None
    token_invalid: bool = False
    retryable: bool = False


class PushProvider:
    name = "abstract"
    def send(self, token, title, body, data): raise NotImplementedError


class DevelopmentPushProvider(PushProvider):
    """Safe local provider: records delivery intent without contacting FCM."""
    name = "development"
    def __init__(self): self.sent = []
    def send(self, token, title, body, data):
        self.sent.append({"token_suffix": token[-6:], "title": title, "body": body, "data": data})
        return PushResult(True, "dev_message_" + uuid.uuid4().hex)


@dataclass(frozen=True)
class NotificationKind:
    """One kind of push the app receives: the switch that allows it, its Android channel and how long it stays useful."""
    type: str
    setting: str
    channel: str
    ttl: timedelta


# Every push the backend sends. The app routes taps by ``data.type`` (notificationRouting.ts) and creates
# one Android channel per kind (MainApplication.kt), so people can mute each kind in the system settings too.
NOTIFICATION_KINDS = {
    "DAILY_BRIEFING": NotificationKind("DAILY_BRIEFING", "daily_briefing_enabled", "daily_briefing", timedelta(hours=3)),
    "BREAKING_NEWS": NotificationKind("BREAKING_NEWS", "breaking_news_enabled", "breaking_news", timedelta(hours=1)),
    # Favourite teams and followed games (football_alerts.py); a late game alert is stale, so they expire fast.
    "TEAM_KICKOFF": NotificationKind("TEAM_KICKOFF", "team_kickoff_enabled", "team_alerts", timedelta(minutes=20)),
    "TEAM_GOAL": NotificationKind("TEAM_GOAL", "team_goals_enabled", "team_alerts", timedelta(minutes=15)),
    "TEAM_FINAL": NotificationKind("TEAM_FINAL", "team_final_enabled", "team_alerts", timedelta(hours=2)),
    "TEAM_NEWS": NotificationKind("TEAM_NEWS", "team_news_enabled", "team_alerts", timedelta(hours=2)),
    # Premium: "começa em 15 min" (football_alerts.py), keywords and followed stories (alerts.py).
    "TEAM_REMINDER": NotificationKind("TEAM_REMINDER", "team_reminder_enabled", "team_alerts", timedelta(minutes=15)),
    "KEYWORD_ALERT": NotificationKind("KEYWORD_ALERT", "keyword_alerts_enabled", "personal_alerts", timedelta(hours=1)),
    "STORY_UPDATE": NotificationKind("STORY_UPDATE", "story_updates_enabled", "personal_alerts", timedelta(hours=2)),
}
# Announcements and promotions are not here: they are sent from the Firebase console to the FCM topics every
# phone joins (mobile/src/push/topics.ts), to everyone whose phone allows notifications, with no switch.
# Every switch and its value for a new account.
SETTING_DEFAULTS = {"notifications_enabled": True, "daily_briefing_enabled": True, "breaking_news_enabled": False,
                    "team_kickoff_enabled": True, "team_goals_enabled": True, "team_final_enabled": True, "team_news_enabled": True,
                    "team_reminder_enabled": True, "keyword_alerts_enabled": True, "story_updates_enabled": True, "live_activities_enabled": True}
SETTING_FIELDS = tuple(SETTING_DEFAULTS)


def notification_kind(data):
    return NOTIFICATION_KINDS.get(str((data or {}).get("type")), NOTIFICATION_KINDS["DAILY_BRIEFING"])


def android_channel(data):
    return notification_kind(data).channel


def wants(settings, notification_type):
    """Whether the user's switches allow this kind of push: the main switch and the kind's own."""
    kind = NOTIFICATION_KINDS.get(notification_type)
    return bool(kind and settings.get("notifications_enabled") and settings.get(kind.setting))


def _minutes(duration_ms):
    return max(1, round((duration_ms or 0) / 60000))


def _period(delivery_time, english):
    hour = int(str(delivery_time or "06:00")[:2])
    if english:
        return "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"
    return "da manhã" if hour < 12 else "da tarde" if hour < 18 else "da noite"


def daily_briefing_message(delivery_id, item_count=None, duration_ms=None, language="pt-BR", kind="SCHEDULED", theme_label=None, delivery_time=None):
    english = str(language or "").lower().startswith("en")
    parts = []
    if item_count:
        parts.append(f"{item_count} {'stories picked for you' if english else 'notícias selecionadas para você'}")
    if duration_ms:
        parts.append(f"{_minutes(duration_ms)} min")
    body = " · ".join(parts) or ("Your daily briefing is ready to start your day." if english else "Seu resumo diário está pronto para começar o dia.")
    # The daily briefing keeps its title; the day's extra ones say which they are (theme or time of day).
    if kind == "ON_DEMAND":
        title = "Your briefing on demand is ready" if english else "Seu resumo na hora está pronto"
    elif kind == "EXTRA" and theme_label:
        title = f"Your {theme_label} briefing is ready" if english else f"Seu resumo de {theme_label} está pronto"
    elif kind == "EXTRA":
        title = f"Your {_period(delivery_time, True)} briefing is ready" if english else f"Seu resumo {_period(delivery_time, False)} está pronto"
    else:
        title = "Your briefing is ready" if english else "Seu resumo de hoje está pronto"
    return {"title": title, "body": body,
            "data": {"type": "DAILY_BRIEFING", "briefing_id": delivery_id, "delivery_id": delivery_id}}


class FCMPushProvider(PushProvider):
    """FCM HTTP v1 through the Firebase Admin SDK.

    The SDK mints and refreshes the short-lived OAuth token from the service account in
    GOOGLE_APPLICATION_CREDENTIALS; credentials stay outside the repository.
    """
    name = "fcm"
    def __init__(self, project_id=None):
        self.project_id = project_id or os.getenv("FCM_PROJECT_ID") or os.getenv("FIREBASE_PROJECT_ID") or None
        self._messaging = None

    def _client(self):
        if self._messaging is None:
            import firebase_admin
            from firebase_admin import messaging
            if not firebase_admin._apps:
                firebase_admin.initialize_app(options={"projectId": self.project_id} if self.project_id else None)
            self._messaging = messaging
        return self._messaging

    def send(self, token, title, body, data):
        try:
            messaging = self._client()
            from firebase_admin import exceptions
        except Exception:
            return PushResult(False, failure_reason="FCM_NOT_CONFIGURED", retryable=False)
        data = dict(data or {}); image = data.pop("image", None); kind = notification_kind(data)
        # A tag per briefing or story: a resend replaces the notification already on screen instead of stacking a copy.
        tag = str(data.get("delivery_id") or data.get("event_id") or kind.type.lower())[:64]
        ttl = int(kind.ttl.total_seconds())
        message = messaging.Message(
            token=token,
            notification=messaging.Notification(title=title, body=body),
            data={str(k): str(v) for k, v in data.items()},
            android=messaging.AndroidConfig(priority="high", ttl=ttl, collapse_key=tag, notification=messaging.AndroidNotification(
                channel_id=kind.channel, tag=tag, image=image, default_sound=True)),
            apns=messaging.APNSConfig(
                headers={"apns-collapse-id": tag, "apns-expiration": str(int(time.time()) + ttl),
                         "apns-priority": "10", "apns-push-type": "alert"},
                payload=messaging.APNSPayload(aps=messaging.Aps(sound="default", thread_id=kind.channel, mutable_content=bool(image)))))
        try:
            return PushResult(True, messaging.send(message))
        except (messaging.UnregisteredError, messaging.SenderIdMismatchError):
            return PushResult(False, failure_reason="TOKEN_INVALID", token_invalid=True)
        except exceptions.InvalidArgumentError as exc:
            # FCM answers INVALID_ARGUMENT for a malformed registration token as well as for a bad payload.
            invalid_token = "registration token" in str(exc).lower()
            return PushResult(False, failure_reason="TOKEN_INVALID" if invalid_token else "PROVIDER_REJECTED", token_invalid=invalid_token)
        except (messaging.QuotaExceededError, exceptions.UnavailableError, exceptions.InternalError, exceptions.DeadlineExceededError):
            return PushResult(False, failure_reason="PROVIDER_UNAVAILABLE", retryable=True)
        except exceptions.FirebaseError:
            return PushResult(False, failure_reason="PROVIDER_REJECTED")
        except Exception as exc:
            if type(exc).__name__ in {"DefaultCredentialsError", "RefreshError"}:
                return PushResult(False, failure_reason="FCM_NOT_CONFIGURED", retryable=False)
            return PushResult(False, failure_reason="PROVIDER_UNAVAILABLE", retryable=True)


class NotificationService:
    def __init__(self, repo, provider=None, late_tolerance_minutes=30):
        self.repo = repo; selected = getattr(getattr(repo, "config", None), "push_provider", os.getenv("PUSH_PROVIDER", "development")); self.provider = provider or (FCMPushProvider() if selected == "fcm" else DevelopmentPushProvider()); self.late_tolerance = timedelta(minutes=late_tolerance_minutes)
        self.breaking_max_delay = timedelta(minutes=max(5, int(os.getenv("BREAKING_MAX_DELAY_MINUTES", "60"))))

    def _event(self, event_type, job_id=None, device_id=None, metadata=None):
        self.repo.db.execute("INSERT INTO notification_events(event_type,job_id,device_id,metadata_json,created_at) VALUES(?,?,?,?,?)", (event_type, job_id, device_id, json.dumps(metadata or {}, ensure_ascii=False), now_iso())); self.repo.db.commit()

    def register_device(self, user_id, data):
        platform = str(data.get("platform", "")).upper(); token = str(data.get("push_token", "")).strip()
        if platform not in {"ANDROID", "IOS"}: raise ValueError("platform must be ANDROID or IOS")
        if not token or len(token) < 10: raise ValueError("push_token is required")
        existing = self.repo.db.execute("SELECT * FROM push_devices WHERE push_token=?", (token,)).fetchone(); t = now_iso()
        did = existing["id"] if existing else "device_" + uuid.uuid4().hex
        if existing and existing["user_id"] != user_id:
            # The same phone signed in with another account: an FCM token identifies the app install,
            # so it now belongs to the authenticated user. The previous owner's queued pushes must not reach it.
            self.repo.db.execute("UPDATE notification_jobs SET status='CANCELLED',last_error='device reassigned to another user',updated_at=? WHERE device_id=? AND user_id<>? AND status IN ('PENDING','RUNNING')", (t, did, user_id))
            self._event("device_reassigned", device_id=did)
        # The app reports the system permission on every launch: a phone where notifications are blocked stays
        # linked to the account but gets no pushes until the permission comes back.
        permitted = str(data.get("permission") or "AUTHORIZED").upper() not in {"DENIED", "NOT_DETERMINED"}
        identifier = str(data.get("device_identifier") or "").strip() or None
        if existing: self.repo.db.execute("UPDATE push_devices SET user_id=?,platform=?,device_identifier=?,app_version=?,locale=?,timezone=?,enabled=?,updated_at=?,last_seen_at=?,invalidated_at=NULL WHERE id=?", (user_id,platform,identifier,data.get("app_version"),data.get("locale"),data.get("timezone","America/Sao_Paulo"),int(permitted),t,t,did))
        else: self.repo.db.execute("INSERT INTO push_devices(id,user_id,platform,push_token,device_identifier,app_version,locale,timezone,enabled,created_at,updated_at,last_seen_at,invalidated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (did,user_id,platform,token,identifier,data.get("app_version"),data.get("locale"),data.get("timezone","America/Sao_Paulo"),int(permitted),t,t,t,None))
        if identifier:
            # The same phone with a new token (reinstall, token rotation): retire the old rows so one push never arrives twice.
            stale = [row["id"] for row in self.repo.db.execute("SELECT id FROM push_devices WHERE user_id=? AND device_identifier=? AND id<>? AND enabled=1", (user_id, identifier, did))]
            for old in stale:
                self.repo.db.execute("UPDATE push_devices SET enabled=0,invalidated_at=?,updated_at=? WHERE id=?", (t, t, old))
                self.repo.db.execute("UPDATE notification_jobs SET status='CANCELLED',last_error='device replaced by a newer token',updated_at=? WHERE device_id=? AND status='PENDING'", (t, old))
        if not permitted:
            self.repo.db.execute("UPDATE notification_jobs SET status='CANCELLED',last_error='notifications blocked on the device',updated_at=? WHERE device_id=? AND status='PENDING'", (t, did))
        self.repo.db.commit(); return self.public_device(self.repo.db.execute("SELECT * FROM push_devices WHERE id=?", (did,)).fetchone())

    @staticmethod
    def public_device(row):
        if not row: return None
        return {k: row[k] for k in ("id","platform","device_identifier","app_version","locale","timezone","enabled","created_at","updated_at","last_seen_at","invalidated_at")}

    def disable_device(self, user_id, device_id):
        cur = self.repo.db.execute("UPDATE push_devices SET enabled=0,invalidated_at=?,updated_at=? WHERE id=? AND user_id=?", (now_iso(),now_iso(),device_id,user_id)); self.repo.db.commit(); return cur.rowcount == 1

    def settings(self, user_id):
        row=self.repo.db.execute("SELECT * FROM notification_settings WHERE user_id=?",(user_id,)).fetchone()
        if not row: self._write_settings(user_id,SETTING_DEFAULTS,overwrite=False); row=self.repo.db.execute("SELECT * FROM notification_settings WHERE user_id=?",(user_id,)).fetchone()
        return {field:bool(row[field]) for field in SETTING_FIELDS}

    def _write_settings(self, user_id, values, overwrite=True):
        columns=",".join(SETTING_FIELDS); marks=",".join("?" for _ in SETTING_FIELDS)
        update=",".join(f"{field}=excluded.{field}" for field in SETTING_FIELDS)+",updated_at=excluded.updated_at"
        self.repo.db.execute(f"INSERT INTO notification_settings(user_id,{columns},updated_at) VALUES(?,{marks},?) ON CONFLICT(user_id) DO "+(f"UPDATE SET {update}" if overwrite else "NOTHING"),
            (user_id,*[int(bool(values[field])) for field in SETTING_FIELDS],now_iso()))
        self.repo.db.commit()

    def public_settings(self, user_id):
        """The switches plus what the screen shows next to them: the briefing time and size and the breaking-news limits."""
        from .breaking import breaking_rules
        prefs = self.repo.db.execute("SELECT briefing_time,briefing_size FROM user_preferences WHERE user_id=?", (user_id,)).fetchone()
        devices = self.repo.db.execute("SELECT COUNT(*) FROM push_devices WHERE user_id=? AND enabled=1 AND invalidated_at IS NULL", (user_id,)).fetchone()[0]
        return {**self.settings(user_id), "briefing_time": prefs["briefing_time"] if prefs else None, "briefing_size": prefs["briefing_size"] if prefs else None,
                "breaking_news_rules": breaking_rules(), "active_devices": devices}

    def save_settings(self, user_id, data):
        if not isinstance(data, dict) or not any(k in data for k in SETTING_FIELDS): raise ValueError("no notification setting to save")
        if any(k in data and not isinstance(data[k], bool) for k in SETTING_FIELDS): raise ValueError("notification settings must be true or false")
        current=self.settings(user_id); current.update({k:data[k] for k in SETTING_FIELDS if k in data})
        self._write_settings(user_id,current); return self.settings(user_id)

    def enqueue_ready(self, now=None):
        now = now or datetime.now(timezone.utc); created=0
        rows=self.repo.db.execute("""SELECT d.*,u.id AS uid FROM user_briefing_deliveries d
            JOIN users u ON u.id=d.user_id JOIN audio_artifacts a ON a.id=d.audio_artifact_id
            JOIN audio_scripts s ON s.id=a.audio_script_id AND s.edition_id=d.edition_id
            WHERE d.status='READY' AND d.audio_status='READY' AND d.active_voice_id=d.selected_voice_id
            AND a.status='READY' AND a.voice=d.active_voice_id AND a.duration_ms>0 AND a.size_bytes>=128""").fetchall()
        for delivery in rows:
            artifact=self.repo.db.execute("SELECT storage_path FROM audio_artifacts WHERE id=?",(delivery["audio_artifact_id"],)).fetchone()
            if not artifact or not os.path.isfile(artifact["storage_path"]): continue
            settings=self.settings(delivery["user_id"])
            if not settings["notifications_enabled"] or not settings["daily_briefing_enabled"]: continue
            local_target=datetime.combine(datetime.fromisoformat(delivery["local_date"]).date(), datetime.strptime(delivery["delivery_time"],"%H:%M").time(), ZoneInfo(delivery["timezone"])); target=local_target.astimezone(timezone.utc); late=now > target + self.late_tolerance
            if late: continue
            devices=self.repo.db.execute("SELECT * FROM push_devices WHERE user_id=? AND enabled=1 AND invalidated_at IS NULL",(delivery["user_id"],)).fetchall()
            for device in devices:
                cur=self.repo.db.execute("INSERT INTO notification_jobs(id,user_id,delivery_id,device_id,notification_type,scheduled_for,status,attempt_count,max_attempts,next_attempt_at,provider_message_id,last_error,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",("notification_"+uuid.uuid4().hex,delivery["user_id"],delivery["id"],device["id"],"DAILY_BRIEFING",iso(target),"PENDING",0,3,None,None,None,now_iso(),now_iso())); created += cur.rowcount
        self.repo.db.commit(); return {"notification_jobs_created":created}

    def run_once(self, now=None):
        now=now or datetime.now(timezone.utc); stale=iso(now-timedelta(minutes=30)); self.repo.db.execute("UPDATE notification_jobs SET status='PENDING',updated_at=?,last_error='stale notification recovered' WHERE status='RUNNING' AND updated_at<? AND attempt_count<max_attempts",(now_iso(),stale)); self.repo.db.commit(); job=self.repo.db.execute("SELECT j.*,d.push_token,d.enabled,d.invalidated_at FROM notification_jobs j JOIN push_devices d ON d.id=j.device_id WHERE j.status='PENDING' AND j.scheduled_for<=? AND (j.next_attempt_at IS NULL OR j.next_attempt_at<=?) ORDER BY j.scheduled_for LIMIT 1",(iso(now),iso(now))).fetchone()
        if not job: return {"jobs_claimed":0,"notifications_sent":0,"notifications_failed":0,"invalid_tokens":0}
        owner=self.repo.db.execute("SELECT user_id FROM push_devices WHERE id=?",(job["device_id"],)).fetchone()
        if not job["enabled"] or job["invalidated_at"] or not owner or owner["user_id"]!=job["user_id"]:
            # Logged-out, invalidated or reassigned device: never deliver this user's briefing to it.
            self.repo.db.execute("UPDATE notification_jobs SET status='CANCELLED',updated_at=?,last_error='device disabled or reassigned' WHERE id=?",(now_iso(),job["id"])); self.repo.db.commit()
            return {"jobs_claimed":1,"notifications_sent":0,"notifications_failed":0,"invalid_tokens":0,"cancelled":1}
        if not wants(self.settings(job["user_id"]),job["notification_type"]):
            # The user turned this kind of notice off after it was queued.
            self.repo.db.execute("UPDATE notification_jobs SET status='CANCELLED',updated_at=?,last_error='turned off in the notification settings' WHERE id=?",(now_iso(),job["id"])); self.repo.db.commit()
            return {"jobs_claimed":1,"notifications_sent":0,"notifications_failed":0,"invalid_tokens":0,"cancelled":1}
        if job["notification_type"]!="DAILY_BRIEFING":
            # Breaking news and team alerts are queued with their message; one delivered late is noise, so it is dropped.
            message=json.loads(job["payload_json"] or "null")
            max_delay=self.breaking_max_delay if job["notification_type"]=="BREAKING_NEWS" else NOTIFICATION_KINDS.get(job["notification_type"],NOTIFICATION_KINDS["BREAKING_NEWS"]).ttl
            if not message or parse(job["scheduled_for"])<now-max_delay:
                self.repo.db.execute("UPDATE notification_jobs SET status='CANCELLED',updated_at=?,last_error='alert is no longer fresh' WHERE id=?",(now_iso(),job["id"])); self.repo.db.commit()
                return {"jobs_claimed":1,"notifications_sent":0,"notifications_failed":0,"invalid_tokens":0,"cancelled":1}
            title,body,data=message["title"],message["body"],message["data"]
        else:
            ready=self.repo.db.execute("""SELECT 1 FROM user_briefing_deliveries d JOIN audio_artifacts a ON a.id=d.audio_artifact_id
                JOIN audio_scripts s ON s.id=a.audio_script_id AND s.edition_id=d.edition_id
                WHERE d.id=? AND d.user_id=? AND d.status='READY' AND d.audio_status='READY'
                AND d.active_voice_id=d.selected_voice_id AND a.voice=d.active_voice_id AND a.status='READY' AND a.duration_ms>0 AND a.size_bytes>=128
                AND a.storage_path IS NOT NULL""",(job["delivery_id"],job["user_id"])).fetchone()
            artifact=self.repo.db.execute("SELECT a.storage_path FROM user_briefing_deliveries d JOIN audio_artifacts a ON a.id=d.audio_artifact_id WHERE d.id=?",(job["delivery_id"],)).fetchone() if ready else None
            if not ready or not artifact or not os.path.isfile(artifact["storage_path"]):
                self.repo.db.execute("UPDATE notification_jobs SET status='CANCELLED',updated_at=?,last_error='delivery audio is no longer READY' WHERE id=?",(now_iso(),job["id"])); self.repo.db.commit()
                return {"jobs_claimed":1,"notifications_sent":0,"notifications_failed":0,"invalid_tokens":0,"cancelled":1}
            info=self.repo.db.execute("""SELECT e.item_count,e.language,a.duration_ms,d.kind,d.theme,d.delivery_time FROM user_briefing_deliveries d
                JOIN briefing_editions e ON e.id=d.edition_id LEFT JOIN audio_artifacts a ON a.id=d.audio_artifact_id WHERE d.id=?""",(job["delivery_id"],)).fetchone()
            theme_label=None
            if info and info["theme"]:
                from newzi_engine.topic_registry import taxonomy
                theme_label=taxonomy().nodes.get(info["theme"],{}).get("name")
            message=daily_briefing_message(job["delivery_id"],info["item_count"] if info else None,info["duration_ms"] if info else None,info["language"] if info else "pt-BR",
                                           info["kind"] if info else "SCHEDULED",theme_label,info["delivery_time"] if info else None)
            title,body,data=message["title"],message["body"],message["data"]
        claimed=self.repo.db.execute("UPDATE notification_jobs SET status='RUNNING',attempt_count=attempt_count+1,updated_at=? WHERE id=? AND status='PENDING'",(now_iso(),job["id"])); self.repo.db.commit()
        if claimed.rowcount!=1:
            # Another worker claimed it between the read and this update.
            return {"jobs_claimed":0,"notifications_sent":0,"notifications_failed":0,"invalid_tokens":0}
        result=self.provider.send(job["push_token"],title,body,data)
        if result.success:
            self.repo.db.execute("UPDATE notification_jobs SET status='SENT',provider_message_id=?,updated_at=? WHERE id=?",(result.provider_message_id,now_iso(),job["id"])); self.repo.db.commit(); self._event("notification_sent",job["id"],job["device_id"],{"provider":self.provider.name,"type":job["notification_type"]}); return {"jobs_claimed":1,"notifications_sent":1,"notifications_failed":0,"invalid_tokens":0}
        if result.token_invalid: self.disable_device(job["user_id"],job["device_id"])
        retry=bool(result.retryable and job["attempt_count"] < job["max_attempts"]); status="PENDING" if retry else "FAILED"; next_at=iso(now+timedelta(minutes=2 ** job["attempt_count"])) if retry else None; self.repo.db.execute("UPDATE notification_jobs SET status=?,next_attempt_at=?,last_error=?,updated_at=? WHERE id=?",(status,next_at,result.failure_reason,now_iso(),job["id"])); self.repo.db.commit(); self._event("notification_failed",job["id"],job["device_id"],{"retry":retry,"token_invalid":result.token_invalid}); return {"jobs_claimed":1,"notifications_sent":0,"notifications_failed":1,"invalid_tokens":1 if result.token_invalid else 0,"retry_count":1 if retry else 0}

    def run_batch(self, limit=200, max_seconds=None, now=None):
        """Deliver up to ``limit`` due notifications within a time budget (one used to go out per worker cycle)."""
        deadline=time.monotonic()+float(max_seconds or os.getenv("NOTIFICATION_BATCH_SECONDS","60"))
        totals={"jobs_claimed":0,"notifications_sent":0,"notifications_failed":0,"invalid_tokens":0}
        for _ in range(max(1,int(limit))):
            result=self.run_once(now)
            for key,value in result.items():
                if isinstance(value,int): totals[key]=totals.get(key,0)+value
            if not result.get("jobs_claimed") or time.monotonic()>deadline: break
        return totals
