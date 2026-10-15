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


# Android channels the app creates (MainApplication.kt); users can mute each kind separately.
ANDROID_CHANNELS = {"BREAKING_NEWS": "breaking_news"}


def android_channel(data):
    return ANDROID_CHANNELS.get(str((data or {}).get("type")), "daily_briefing")


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
        message = messaging.Message(
            token=token,
            notification=messaging.Notification(title=title, body=body),
            data={str(k): str(v) for k, v in data.items()},
            android=messaging.AndroidConfig(priority="high", notification=messaging.AndroidNotification(channel_id=android_channel(data))),
            apns=messaging.APNSConfig(payload=messaging.APNSPayload(aps=messaging.Aps(sound="default"))))
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
        if existing: self.repo.db.execute("UPDATE push_devices SET user_id=?,platform=?,device_identifier=?,app_version=?,locale=?,timezone=?,enabled=1,updated_at=?,last_seen_at=?,invalidated_at=NULL WHERE id=?", (user_id,platform,data.get("device_identifier"),data.get("app_version"),data.get("locale"),data.get("timezone","America/Sao_Paulo"),t,t,did))
        else: self.repo.db.execute("INSERT INTO push_devices(id,user_id,platform,push_token,device_identifier,app_version,locale,timezone,enabled,created_at,updated_at,last_seen_at,invalidated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (did,user_id,platform,token,data.get("device_identifier"),data.get("app_version"),data.get("locale"),data.get("timezone","America/Sao_Paulo"),1,t,t,t,None))
        self.repo.db.commit(); return self.public_device(self.repo.db.execute("SELECT * FROM push_devices WHERE id=?", (did,)).fetchone())

    @staticmethod
    def public_device(row):
        if not row: return None
        return {k: row[k] for k in ("id","platform","device_identifier","app_version","locale","timezone","enabled","created_at","updated_at","last_seen_at","invalidated_at")}

    def disable_device(self, user_id, device_id):
        cur = self.repo.db.execute("UPDATE push_devices SET enabled=0,invalidated_at=?,updated_at=? WHERE id=? AND user_id=?", (now_iso(),now_iso(),device_id,user_id)); self.repo.db.commit(); return cur.rowcount == 1

    def settings(self, user_id):
        row=self.repo.db.execute("SELECT * FROM notification_settings WHERE user_id=?",(user_id,)).fetchone()
        if not row: self.repo.db.execute("INSERT INTO notification_settings(user_id,notifications_enabled,daily_briefing_enabled,breaking_news_enabled,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO NOTHING",(user_id,1,1,0,now_iso())); self.repo.db.commit(); row=self.repo.db.execute("SELECT * FROM notification_settings WHERE user_id=?",(user_id,)).fetchone()
        return {"notifications_enabled":bool(row["notifications_enabled"]),"daily_briefing_enabled":bool(row["daily_briefing_enabled"]),"breaking_news_enabled":bool(row["breaking_news_enabled"])}

    def save_settings(self, user_id, data):
        current=self.settings(user_id); current.update({k:bool(data[k]) for k in ("notifications_enabled","daily_briefing_enabled","breaking_news_enabled") if k in data}); t=now_iso(); self.repo.db.execute("INSERT INTO notification_settings(user_id,notifications_enabled,daily_briefing_enabled,breaking_news_enabled,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET notifications_enabled=excluded.notifications_enabled,daily_briefing_enabled=excluded.daily_briefing_enabled,breaking_news_enabled=excluded.breaking_news_enabled,updated_at=excluded.updated_at",(user_id,int(current["notifications_enabled"]),int(current["daily_briefing_enabled"]),int(current["breaking_news_enabled"]),t)); self.repo.db.commit(); return self.settings(user_id)

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
        if job["notification_type"]=="BREAKING_NEWS":
            message=json.loads(job["payload_json"] or "null")
            if not message or parse(job["scheduled_for"])<now-self.breaking_max_delay:
                # A breaking alert delivered hours late is noise; drop it instead.
                self.repo.db.execute("UPDATE notification_jobs SET status='CANCELLED',updated_at=?,last_error='breaking news is no longer fresh' WHERE id=?",(now_iso(),job["id"])); self.repo.db.commit()
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
            title,body,data="Seu resumo está pronto","Seu resumo diário está pronto para começar o dia.",{"type":"DAILY_BRIEFING","briefing_id":job["delivery_id"],"delivery_id":job["delivery_id"]}
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
