"""Phase 4.7 push delivery foundation with provider and device boundaries."""
import json, os, uuid
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from zoneinfo import ZoneInfo


def now_iso(): return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


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


class FCMPushProvider(PushProvider):
    """FCM HTTP v1 boundary; credentials stay outside the repository."""
    name = "fcm"
    def send(self, token, title, body, data):
        if not os.getenv("FCM_ACCESS_TOKEN") or not os.getenv("FCM_PROJECT_ID"):
            return PushResult(False, failure_reason="FCM_NOT_CONFIGURED", retryable=False)
        try:
            import httpx
            response = httpx.post(f"https://fcm.googleapis.com/v1/projects/{os.environ['FCM_PROJECT_ID']}/messages:send", headers={"Authorization": f"Bearer {os.environ['FCM_ACCESS_TOKEN']}", "Content-Type": "application/json"}, json={"message": {"token": token, "notification": {"title": title, "body": body}, "data": {str(k): str(v) for k, v in data.items()}}}, timeout=10)
            if response.status_code in {404, 410}: return PushResult(False, failure_reason="TOKEN_INVALID", token_invalid=True)
            if response.status_code >= 500: return PushResult(False, failure_reason="PROVIDER_UNAVAILABLE", retryable=True)
            if response.status_code >= 400: return PushResult(False, failure_reason="PROVIDER_REJECTED")
            return PushResult(True, (response.json().get("name") if response.content else None))
        except Exception:
            return PushResult(False, failure_reason="PROVIDER_UNAVAILABLE", retryable=True)


def ensure_notification_schema(repo):
    repo.db.executescript("""
    CREATE TABLE IF NOT EXISTS push_devices(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,platform TEXT NOT NULL,push_token TEXT NOT NULL,device_identifier TEXT,app_version TEXT,locale TEXT,timezone TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,last_seen_at TEXT NOT NULL,invalidated_at TEXT,UNIQUE(push_token));
    CREATE TABLE IF NOT EXISTS notification_settings(user_id TEXT PRIMARY KEY,notifications_enabled INTEGER NOT NULL DEFAULT 1,daily_briefing_enabled INTEGER NOT NULL DEFAULT 1,breaking_news_enabled INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS notification_jobs(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,delivery_id TEXT NOT NULL,device_id TEXT NOT NULL,notification_type TEXT NOT NULL,scheduled_for TEXT NOT NULL,status TEXT NOT NULL,attempt_count INTEGER NOT NULL DEFAULT 0,max_attempts INTEGER NOT NULL DEFAULT 3,next_attempt_at TEXT,provider_message_id TEXT,last_error TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(delivery_id,device_id,notification_type));
    CREATE TABLE IF NOT EXISTS notification_events(id INTEGER PRIMARY KEY AUTOINCREMENT,event_type TEXT NOT NULL,job_id TEXT,device_id TEXT,metadata_json TEXT NOT NULL,created_at TEXT NOT NULL);
    """)
    repo.db.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(4,?)", (now_iso(),)); repo.db.commit()


class NotificationService:
    def __init__(self, repo, provider=None, late_tolerance_minutes=30):
        ensure_notification_schema(repo); self.repo = repo; selected = getattr(getattr(repo, "config", None), "push_provider", os.getenv("PUSH_PROVIDER", "development")); self.provider = provider or (FCMPushProvider() if selected == "fcm" else DevelopmentPushProvider()); self.late_tolerance = timedelta(minutes=late_tolerance_minutes)

    def _event(self, event_type, job_id=None, device_id=None, metadata=None):
        self.repo.db.execute("INSERT INTO notification_events(event_type,job_id,device_id,metadata_json,created_at) VALUES(?,?,?,?,?)", (event_type, job_id, device_id, json.dumps(metadata or {}, ensure_ascii=False), now_iso())); self.repo.db.commit()

    def register_device(self, user_id, data):
        platform = str(data.get("platform", "")).upper(); token = str(data.get("push_token", "")).strip()
        if platform not in {"ANDROID", "IOS"}: raise ValueError("platform must be ANDROID or IOS")
        if not token or len(token) < 10: raise ValueError("push_token is required")
        existing = self.repo.db.execute("SELECT * FROM push_devices WHERE push_token=?", (token,)).fetchone(); t = now_iso()
        if existing and existing["user_id"] != user_id: raise PermissionError("push token already belongs to another user")
        did = existing["id"] if existing else "device_" + uuid.uuid4().hex
        if existing: self.repo.db.execute("UPDATE push_devices SET platform=?,device_identifier=?,app_version=?,locale=?,timezone=?,enabled=1,updated_at=?,last_seen_at=?,invalidated_at=NULL WHERE id=?", (platform,data.get("device_identifier"),data.get("app_version"),data.get("locale"),data.get("timezone","America/Sao_Paulo"),t,t,did))
        else: self.repo.db.execute("INSERT INTO push_devices VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (did,user_id,platform,token,data.get("device_identifier"),data.get("app_version"),data.get("locale"),data.get("timezone","America/Sao_Paulo"),1,t,t,t,None))
        self.repo.db.commit(); return self.public_device(self.repo.db.execute("SELECT * FROM push_devices WHERE id=?", (did,)).fetchone())

    @staticmethod
    def public_device(row):
        if not row: return None
        return {k: row[k] for k in ("id","platform","device_identifier","app_version","locale","timezone","enabled","created_at","updated_at","last_seen_at","invalidated_at")}

    def disable_device(self, user_id, device_id):
        cur = self.repo.db.execute("UPDATE push_devices SET enabled=0,invalidated_at=?,updated_at=? WHERE id=? AND user_id=?", (now_iso(),now_iso(),device_id,user_id)); self.repo.db.commit(); return cur.rowcount == 1

    def settings(self, user_id):
        row=self.repo.db.execute("SELECT * FROM notification_settings WHERE user_id=?",(user_id,)).fetchone()
        if not row: self.repo.db.execute("INSERT INTO notification_settings VALUES(?,?,?,?,?)",(user_id,1,1,0,now_iso())); self.repo.db.commit(); row=self.repo.db.execute("SELECT * FROM notification_settings WHERE user_id=?",(user_id,)).fetchone()
        return {"notifications_enabled":bool(row["notifications_enabled"]),"daily_briefing_enabled":bool(row["daily_briefing_enabled"]),"breaking_news_enabled":bool(row["breaking_news_enabled"])}

    def save_settings(self, user_id, data):
        current=self.settings(user_id); current.update({k:bool(data[k]) for k in ("notifications_enabled","daily_briefing_enabled","breaking_news_enabled") if k in data}); t=now_iso(); self.repo.db.execute("INSERT OR REPLACE INTO notification_settings VALUES(?,?,?,?,?)",(user_id,int(current["notifications_enabled"]),int(current["daily_briefing_enabled"]),int(current["breaking_news_enabled"]),t)); self.repo.db.commit(); return self.settings(user_id)

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
                cur=self.repo.db.execute("INSERT OR IGNORE INTO notification_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",("notification_"+uuid.uuid4().hex,delivery["user_id"],delivery["id"],device["id"],"DAILY_BRIEFING",target.isoformat(),"PENDING",0,3,None,None,None,now_iso(),now_iso())); created += cur.rowcount
        self.repo.db.commit(); return {"notification_jobs_created":created}

    def run_once(self, now=None):
        now=now or datetime.now(timezone.utc); stale=(now-timedelta(minutes=30)).isoformat(); self.repo.db.execute("UPDATE notification_jobs SET status='PENDING',updated_at=?,last_error='stale notification recovered' WHERE status='RUNNING' AND updated_at<? AND attempt_count<max_attempts",(now_iso(),stale)); self.repo.db.commit(); job=self.repo.db.execute("SELECT j.*,d.push_token,d.enabled,d.invalidated_at FROM notification_jobs j JOIN push_devices d ON d.id=j.device_id WHERE j.status='PENDING' AND j.scheduled_for<=? AND (j.next_attempt_at IS NULL OR j.next_attempt_at<=?) ORDER BY j.scheduled_for LIMIT 1",(now.isoformat(),now.isoformat())).fetchone()
        if not job: return {"jobs_claimed":0,"notifications_sent":0,"notifications_failed":0,"invalid_tokens":0}
        ready=self.repo.db.execute("""SELECT 1 FROM user_briefing_deliveries d JOIN audio_artifacts a ON a.id=d.audio_artifact_id
            JOIN audio_scripts s ON s.id=a.audio_script_id AND s.edition_id=d.edition_id
            WHERE d.id=? AND d.user_id=? AND d.status='READY' AND d.audio_status='READY'
            AND d.active_voice_id=d.selected_voice_id AND a.voice=d.active_voice_id AND a.status='READY' AND a.duration_ms>0 AND a.size_bytes>=128
            AND a.storage_path IS NOT NULL""",(job["delivery_id"],job["user_id"])).fetchone()
        artifact=self.repo.db.execute("SELECT a.storage_path FROM user_briefing_deliveries d JOIN audio_artifacts a ON a.id=d.audio_artifact_id WHERE d.id=?",(job["delivery_id"],)).fetchone() if ready else None
        if not ready or not artifact or not os.path.isfile(artifact["storage_path"]):
            self.repo.db.execute("UPDATE notification_jobs SET status='CANCELLED',updated_at=?,last_error='delivery audio is no longer READY' WHERE id=?",(now_iso(),job["id"])); self.repo.db.commit()
            return {"jobs_claimed":1,"notifications_sent":0,"notifications_failed":0,"invalid_tokens":0,"cancelled":1}
        self.repo.db.execute("UPDATE notification_jobs SET status='RUNNING',attempt_count=attempt_count+1,updated_at=? WHERE id=?",(now_iso(),job["id"])); self.repo.db.commit(); result=self.provider.send(job["push_token"],"Seu briefing está pronto","Seu briefing diário está pronto para começar o dia.",{"type":"DAILY_BRIEFING","briefing_id":job["delivery_id"],"delivery_id":job["delivery_id"]})
        if result.success:
            self.repo.db.execute("UPDATE notification_jobs SET status='SENT',provider_message_id=?,updated_at=? WHERE id=?",(result.provider_message_id,now_iso(),job["id"])); self.repo.db.commit(); self._event("notification_sent",job["id"],job["device_id"],{"provider":self.provider.name}); return {"jobs_claimed":1,"notifications_sent":1,"notifications_failed":0,"invalid_tokens":0}
        if result.token_invalid: self.disable_device(job["user_id"],job["device_id"])
        retry=bool(result.retryable and job["attempt_count"] < job["max_attempts"]); status="PENDING" if retry else "FAILED"; next_at=(now+timedelta(minutes=2 ** job["attempt_count"])).isoformat() if retry else None; self.repo.db.execute("UPDATE notification_jobs SET status=?,next_attempt_at=?,last_error=?,updated_at=? WHERE id=?",(status,next_at,result.failure_reason,now_iso(),job["id"])); self.repo.db.commit(); self._event("notification_failed",job["id"],job["device_id"],{"retry":retry,"token_invalid":result.token_invalid}); return {"jobs_claimed":1,"notifications_sent":0,"notifications_failed":1,"invalid_tokens":1 if result.token_invalid else 0,"retry_count":1 if retry else 0}

