"""Phase 4.2 scheduling, shared editions and asynchronous generation worker."""
import hashlib, json, os, sqlite3, uuid
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from .paths import BACKEND_DATA
from newzi_engine.paths import ENGINE_OUTPUT, ENGINE_ROOT
from newzi_engine.topic_registry import taxonomy

from .product_backend import ProductRepository, Phase33Adapter, validate_timezone

MINIMUM_DELIVERABLE_ITEMS = 1
PROFILE_SCHEMA_VERSION = "7.0.0"


class GenerationError(RuntimeError):
    def __init__(self, code, message): self.code=code; super().__init__(message)


@dataclass(frozen=True)
class BriefingProfile:
    topics: tuple
    language: str
    briefing_size: int
    country_scope: str
    def key(self):
        raw={"profile_schema_version":PROFILE_SCHEMA_VERSION,"topics":taxonomy().canonicalize(self.topics)[0],"language":self.language,"briefing_size":self.briefing_size,"country_scope":self.country_scope}
        return "profile_"+hashlib.sha256(json.dumps(raw,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
    @classmethod
    def from_preferences(cls, prefs):
        topics = () if prefs.get("content_scope") == "all" else taxonomy().canonicalize(prefs["topics"])[0]
        return cls(topics,prefs["language"],int(prefs["briefing_size"]),prefs["country_scope"])


class Clock:
    def now(self, tz=None):
        value=datetime.now(timezone.utc)
        return value.astimezone(ZoneInfo(tz)) if tz else value


class FixedClock(Clock):
    def __init__(self, value): self.value=value
    def now(self, tz=None):
        value=self.value
        if value.tzinfo is None: value=value.replace(tzinfo=timezone.utc)
        return value.astimezone(ZoneInfo(tz)) if tz else value


def ensure_phase42_schema(repo):
    repo.db.executescript("""
    CREATE TABLE IF NOT EXISTS generation_jobs(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,briefing_date TEXT NOT NULL,scheduled_for TEXT NOT NULL,delivery_time TEXT NOT NULL,timezone TEXT NOT NULL,status TEXT NOT NULL,attempt_count INTEGER NOT NULL DEFAULT 0,max_attempts INTEGER NOT NULL DEFAULT 2,created_at TEXT NOT NULL,started_at TEXT,finished_at TEXT,next_retry_at TEXT,error_code TEXT,error_message TEXT,profile_key TEXT NOT NULL,worker_id TEXT,UNIQUE(user_id,briefing_date));
    CREATE TABLE IF NOT EXISTS briefing_editions(id TEXT PRIMARY KEY,profile_key TEXT NOT NULL,edition_date TEXT NOT NULL,language TEXT NOT NULL,status TEXT NOT NULL,generated_at TEXT,item_count INTEGER NOT NULL DEFAULT 0,engine_version TEXT,created_at TEXT NOT NULL,UNIQUE(profile_key,edition_date));
    CREATE TABLE IF NOT EXISTS briefing_edition_items(id TEXT PRIMARY KEY,edition_id TEXT NOT NULL,position INTEGER NOT NULL,event_id TEXT,headline TEXT,summary TEXT,why_it_matters TEXT,key_points_json TEXT,confidence REAL,evidence_quality TEXT,trace_id TEXT,warnings_json TEXT,sources_json TEXT NOT NULL DEFAULT '[]',created_at TEXT NOT NULL,primary_taxonomy_id TEXT,primary_taxonomy_label TEXT,primary_taxonomy_reason TEXT,matched_taxonomy_ids_json TEXT,user_interest_matches_json TEXT);
    CREATE TABLE IF NOT EXISTS user_briefing_deliveries(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,edition_id TEXT NOT NULL,local_date TEXT NOT NULL,delivery_time TEXT NOT NULL,timezone TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,delivered_at TEXT,UNIQUE(user_id,local_date));
    CREATE TABLE IF NOT EXISTS profile_taxonomy(profile_key TEXT NOT NULL,taxonomy_id TEXT NOT NULL,PRIMARY KEY(profile_key,taxonomy_id));
    CREATE TABLE IF NOT EXISTS generation_job_phases(id INTEGER PRIMARY KEY AUTOINCREMENT,job_id TEXT NOT NULL,phase TEXT NOT NULL,duration_ms INTEGER NOT NULL,recorded_at TEXT NOT NULL,UNIQUE(job_id,phase));
    CREATE TABLE IF NOT EXISTS manual_refresh_requests(
      id TEXT PRIMARY KEY,user_id TEXT NOT NULL,reason TEXT NOT NULL DEFAULT 'MANUAL_REFRESH',status TEXT NOT NULL,
      stage TEXT NOT NULL,requested_at TEXT NOT NULL,started_at TEXT,updated_at TEXT NOT NULL,finished_at TEXT,
      ingestion_run_id TEXT,edition_id TEXT,audio_job_id TEXT,selected_voice_id TEXT,audio_variant_id TEXT,
      error_code TEXT,error_message TEXT);
    CREATE INDEX IF NOT EXISTS idx_manual_refresh_active ON manual_refresh_requests(user_id,status,requested_at);
    CREATE TABLE IF NOT EXISTS content_ingestion_runs(
      id TEXT PRIMARY KEY,status TEXT NOT NULL,started_at TEXT NOT NULL,completed_at TEXT,
      sources_attempted INTEGER NOT NULL DEFAULT 0,sources_successful INTEGER NOT NULL DEFAULT 0,
      articles_seen INTEGER NOT NULL DEFAULT 0,articles_new INTEGER NOT NULL DEFAULT 0,
      articles_updated INTEGER NOT NULL DEFAULT 0,articles_unchanged INTEGER NOT NULL DEFAULT 0,
      errors_json TEXT NOT NULL DEFAULT '{}',source_metrics_json TEXT NOT NULL DEFAULT '[]');
    CREATE TABLE IF NOT EXISTS briefing_listening_progress(
      delivery_id TEXT NOT NULL,user_id TEXT NOT NULL,progress_seconds REAL NOT NULL DEFAULT 0,
      duration_seconds REAL NOT NULL DEFAULT 0,completed_at TEXT,updated_at TEXT NOT NULL,
      PRIMARY KEY(delivery_id,user_id));
    """)
    repo.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_content_ingestion ON content_ingestion_runs(status) WHERE status='RUNNING'")
    ingestion_columns={row[1] for row in repo.db.execute("PRAGMA table_info(content_ingestion_runs)")}
    if "source_metrics_json" not in ingestion_columns:
        repo.db.execute("ALTER TABLE content_ingestion_runs ADD COLUMN source_metrics_json TEXT NOT NULL DEFAULT '[]'")
    delivery_columns={row[1] for row in repo.db.execute("PRAGMA table_info(user_briefing_deliveries)")}
    delivery_additions={
        "selected_voice_id":"TEXT", "active_voice_id":"TEXT", "audio_artifact_id":"TEXT",
        "audio_status":"TEXT NOT NULL DEFAULT 'PENDING'", "generation_stage":"TEXT",
        "generation_started_at":"TEXT", "generation_updated_at":"TEXT",
        "generation_error_code":"TEXT", "generation_error_message":"TEXT", "script_id":"TEXT",
        "voice_fallback_reason":"TEXT"
    }
    for name, declaration in delivery_additions.items():
        if name not in delivery_columns:
            repo.db.execute(f"ALTER TABLE user_briefing_deliveries ADD COLUMN {name} {declaration}")
    repo.db.execute("UPDATE user_briefing_deliveries SET status='CONTENT_READY',audio_status='PENDING',generation_stage='AUDIO_QUEUED',generation_started_at=COALESCE(generation_started_at,created_at),generation_updated_at=COALESCE(generation_updated_at,created_at) WHERE status='READY' AND audio_artifact_id IS NULL")
    columns={row[1] for row in repo.db.execute("PRAGMA table_info(briefing_edition_items)")}
    for name in ("primary_taxonomy_id", "primary_taxonomy_label", "primary_taxonomy_reason",
                 "matched_taxonomy_ids_json", "user_interest_matches_json"):
        if name not in columns:
            repo.db.execute(f"ALTER TABLE briefing_edition_items ADD COLUMN {name} TEXT")
    repo.db.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(2,datetime('now'))")
    repo.db.commit()


class FixtureBriefingGenerator:
    def __init__(self,path=None): self.path=Path(path or (ENGINE_ROOT / "fixtures" / "briefing.json")); self.calls=0
    def generate(self, topics, language, briefing_size, date, country_scope="BOTH"):
        self.calls+=1
        data=json.loads(self.path.read_text(encoding="utf-8")); items=data.get("items",[])[:briefing_size]
        return {"status":"READY" if items else "PARTIAL","generated_at":data.get("generated_at"),"engine_version":"phase_3.3-fixture","items":items}


class EngineBriefingGenerator:
    def __init__(self, repo=None): self.calls=0; self.repo=repo; self.last_sync=None; self.sync_metrics={}; self.last_phase_durations={}
    def generate(self, topics, language, briefing_size, date, country_scope="BOTH"):
        self.calls+=1
        try:
            from .content import compose, sync_semantic_output
            if self.repo is None: raise GenerationError("CONFIG_ERROR", "content repository unavailable")
            now=datetime.now(timezone.utc)
            self.last_phase_durations.setdefault("CONTENT_REFRESH",0)
            phase=time.monotonic(); self.sync_metrics["semantic_cache_imports"]=sync_semantic_output(self.repo); self.last_phase_durations["SEMANTIC_ENRICHMENT"]=int((time.monotonic()-phase)*1000)
            phase=time.monotonic(); result=compose(self.repo,topics,language,briefing_size,country_scope,now)
            self.last_phase_durations["CONTENT_COMPOSITION"]=int((time.monotonic()-phase)*1000)
            return result
        except GenerationError: raise
        except Exception as exc: raise GenerationError("ENGINE_FAILED",str(exc))


class BriefingScheduler:
    def __init__(self, repo, clock=None, lead_minutes=None, max_attempts=None):
        self.repo=repo; ensure_phase42_schema(repo); self.clock=clock or Clock(); self._lead_override=lead_minutes if lead_minutes is not None else os.getenv("BRIEFING_GENERATION_LEAD_MINUTES"); self.lead_minutes=int(self._lead_override) if self._lead_override is not None else self._measured_lead_minutes(); self.max_attempts=int(max_attempts if max_attempts is not None else os.getenv("GENERATION_MAX_RETRIES",2))
    @staticmethod
    def _p95(values):
        numbers=sorted(int(value or 0) for value in values if value is not None and int(value or 0)>0)
        return numbers[min(len(numbers)-1, max(0, int(len(numbers)*.95)-1))] if numbers else None
    def _measured_lead_minutes(self):
        fallback=max(1,int(os.getenv("BRIEFING_GENERATION_LEAD_FALLBACK_MINUTES","10")))
        safety=max(0,int(os.getenv("BRIEFING_GENERATION_SAFETY_MINUTES","2")))
        try:
            ingestion=[r[0] for r in self.repo.db.execute("SELECT (julianday(completed_at)-julianday(started_at))*86400000 FROM content_ingestion_runs WHERE status='READY' AND completed_at IS NOT NULL ORDER BY started_at DESC LIMIT 100")]
            composition=[r[0] for r in self.repo.db.execute("SELECT duration_ms FROM generation_job_phases WHERE phase='TOTAL_DELIVERY_CONTENT' ORDER BY recorded_at DESC LIMIT 100")]
            audio=[r[0] for r in self.repo.db.execute("SELECT duration_ms FROM audio_job_phases WHERE phase IN ('TTS','VALIDATION','STORAGE') ORDER BY id DESC LIMIT 300")]
            p95=sum(x or 0 for x in (self._p95(ingestion),self._p95(composition),self._p95(audio)))
            if p95<=0: return fallback
            return max(1,min(180,(p95+59_999)//60_000+safety))
        except sqlite3.OperationalError:
            return fallback
    def _eligible(self,prefs, now):
        local=now.astimezone(ZoneInfo(prefs["timezone"])); delivery=datetime.combine(local.date(),datetime.strptime(prefs["briefing_time"],"%H:%M").time(),ZoneInfo(prefs["timezone"])); return local >= delivery-timedelta(minutes=self.lead_minutes), local.date().isoformat(), delivery
    def run_once(self):
        self.lead_minutes=int(self._lead_override) if self._lead_override is not None else self._measured_lead_minutes()
        run_id="scheduler_"+uuid.uuid4().hex; discovered=created=skipped=0; rows=self.repo.db.execute("SELECT u.id FROM users u WHERE u.status='ACTIVE'").fetchall()
        for row in rows:
            uid=row["id"]; prefs=self.repo.get_preferences(uid); eligible,local_date,delivery=self._eligible(prefs,self.clock.now("UTC"));
            if not eligible: continue
            discovered+=1; existing=self.repo.db.execute("SELECT id FROM generation_jobs WHERE user_id=? AND briefing_date=?",(uid,local_date)).fetchone()
            profile=BriefingProfile.from_preferences(prefs)
            self.repo.db.executemany("INSERT OR IGNORE INTO profile_taxonomy VALUES(?,?)", [(profile.key(), topic) for topic in profile.topics])
            if existing:
                previous=self.repo.db.execute("SELECT profile_key,status FROM generation_jobs WHERE id=?",(existing["id"],)).fetchone()
                if previous["profile_key"]!=profile.key() and previous["status"]!="RUNNING":
                    self.repo.db.execute("UPDATE generation_jobs SET profile_key=?,status='PENDING',attempt_count=0,error_code=NULL,error_message=NULL,next_retry_at=NULL WHERE id=?",(profile.key(),existing["id"])); created+=1
                else: skipped+=1
                continue
            scheduled=(delivery-timedelta(minutes=self.lead_minutes)).astimezone(timezone.utc).isoformat(); self.repo.db.execute("INSERT INTO generation_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",("job_"+uuid.uuid4().hex,uid,local_date,scheduled,prefs["briefing_time"],prefs["timezone"],"PENDING",0,self.max_attempts,datetime.now(timezone.utc).isoformat(),None,None,None,None,None,profile.key(),None)); created+=1
        self.repo.db.commit(); return {"scheduler_run_id":run_id,"jobs_discovered":discovered,"jobs_created":created,"jobs_skipped_existing":skipped,"lead_minutes":self.lead_minutes}

    def schedule_user_now(self, user_id):
        """Idempotently schedule a first/current-day edition after onboarding or profile changes."""
        prefs=self.repo.get_preferences(user_id)
        if not prefs or (prefs.get("content_scope", "selected") != "all" and not prefs.get("topics")):
            return {"scheduled":False,"reason":"PREFERENCES_INCOMPLETE"}
        from .scheduling import BriefingProfile
        profile=BriefingProfile.from_preferences(prefs)
        local_now=self.clock.now("UTC").astimezone(ZoneInfo(prefs["timezone"]))
        local_date=local_now.date().isoformat()
        self.repo.db.executemany("INSERT OR IGNORE INTO profile_taxonomy VALUES(?,?)",[(profile.key(),topic) for topic in profile.topics])
        existing=self.repo.db.execute("SELECT id,profile_key,status FROM generation_jobs WHERE user_id=? AND briefing_date=?",(user_id,local_date)).fetchone()
        if existing:
            if existing["profile_key"]==profile.key() and existing["status"] in ("PENDING","RUNNING","COMPLETED"):
                self.repo.db.commit(); return {"scheduled":False,"reason":"ALREADY_SCHEDULED","job_id":existing["id"]}
            if existing["status"]=="RUNNING":
                self.repo.db.commit(); return {"scheduled":False,"reason":"ALREADY_RUNNING","job_id":existing["id"]}
            self.repo.db.execute("UPDATE generation_jobs SET profile_key=?,status='PENDING',attempt_count=0,scheduled_for=?,finished_at=NULL,next_retry_at=NULL,error_code=NULL,error_message=NULL WHERE id=?",(profile.key(),datetime.now(timezone.utc).isoformat(),existing["id"]))
            self.repo.db.commit(); return {"scheduled":True,"job_id":existing["id"]}
        job_id="job_"+uuid.uuid4().hex
        self.repo.db.execute("INSERT INTO generation_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(job_id,user_id,local_date,datetime.now(timezone.utc).isoformat(),prefs["briefing_time"],prefs["timezone"],"PENDING",0,self.max_attempts,datetime.now(timezone.utc).isoformat(),None,None,None,None,None,profile.key(),None))
        self.repo.db.commit(); return {"scheduled":True,"job_id":job_id}

    def run_forever(self, interval_seconds=None):
        interval = max(1.0, float(interval_seconds or os.getenv("SCHEDULER_POLL_SECONDS", "60")))
        try:
            while True:
                self.run_once()
                time.sleep(interval)
        except KeyboardInterrupt:
            return


class NewsRefreshWorker:
    """Refresh the shared article pool on a bounded cadence, independently of users."""
    def __init__(self, repo, interval_seconds=None):
        from .content import ensure_content_schema
        self.repo=repo
        self.interval_seconds=max(30,int(interval_seconds if interval_seconds is not None else os.getenv("NEWS_REFRESH_INTERVAL_SECONDS","600")))
        ensure_phase42_schema(repo)
        ensure_content_schema(repo)

    def refresh_if_due(self, force=False):
        now=datetime.now(timezone.utc); now_iso=now.isoformat(); refresh_id=None
        self.repo.db.execute("BEGIN IMMEDIATE")
        try:
            running=self.repo.db.execute("SELECT * FROM content_ingestion_runs WHERE status='RUNNING' ORDER BY started_at DESC LIMIT 1").fetchone()
            if running:
                self.repo.db.commit()
                return {**dict(running),"skipped":"IN_PROGRESS"}
            last=self.repo.db.execute("SELECT * FROM content_ingestion_runs ORDER BY started_at DESC LIMIT 1").fetchone()
            if not force and last and last["completed_at"]:
                completed=datetime.fromisoformat(last["completed_at"].replace("Z","+00:00"))
                if completed.tzinfo is None: completed=completed.replace(tzinfo=timezone.utc)
                backoff=self.interval_seconds if last["status"] in {"READY","PARTIAL"} else min(self.interval_seconds,120)
                if (now-completed).total_seconds()<backoff:
                    self.repo.db.commit()
                    return {**dict(last),"skipped":"NOT_DUE"}
            refresh_id="ingestion_"+uuid.uuid4().hex
            self.repo.db.execute("INSERT INTO content_ingestion_runs(id,status,started_at) VALUES(?,'RUNNING',?)",(refresh_id,now_iso))
            self.repo.db.commit()
        except Exception:
            self.repo.db.rollback(); raise

        total_started=time.monotonic()
        try:
            import runpy
            collect_sources=runpy.run_path(str(ENGINE_ROOT/"main.py"))["collect_sources"]
            try: stats,changed=collect_sources(incremental=True)
            except TypeError: stats,changed=collect_sources()
            from .content import sync_content_incremental, get_content_revision
            revision_before=get_content_revision(self.repo)["revision"]
            index_started=time.monotonic(); index=sync_content_incremental(self.repo,changed,ingestion_run_id=refresh_id)
            index_ms=int((time.monotonic()-index_started)*1000); revision_after=get_content_revision(self.repo)["revision"]
            completed=datetime.now(timezone.utc).isoformat(); source_errors=stats.get("source_errors",{})
            sources_seen=int(stats.get("sources_checked",len(stats.get("source_metrics",[]))))
            sources_successful=int(stats.get("sources_successful",max(0,sources_seen-len(source_errors))))
            status="PARTIAL" if source_errors else "READY"
            phases={"collection_total_ms":stats.get("collection_total_ms"),"index_ms":index_ms,
                "revision_before":revision_before,"revision_after":revision_after,
                "article_image_enrichment":stats.get("article_image_enrichment",{}),
                "classification_ms":index.get("classification_ms",0),
                "index_total_ms":index.get("index_total_ms",index_ms),
                "clustering":index.get("clustering",{}),"index_metrics":index,
                "worker_total_ms":int((time.monotonic()-total_started)*1000)}
            self.repo.db.execute("UPDATE content_ingestion_runs SET status=?,completed_at=?,sources_attempted=?,sources_successful=?,articles_seen=?,articles_new=?,articles_updated=?,articles_unchanged=?,errors_json=?,source_metrics_json=? WHERE id=?",
                (status,completed,sources_seen,sources_successful,int(index.get("articles_seen",0)),int(index.get("articles_new",0)),int(index.get("articles_updated",0)),int(index.get("articles_unchanged",0)),json.dumps({"source_errors":source_errors,"phases":phases},ensure_ascii=False),json.dumps(stats.get("source_metrics",[]),ensure_ascii=False),refresh_id))
            self.repo.db.commit()
            import logging
            logging.getLogger(__name__).info("news refresh %s status=%s sources=%s/%s articles_new=%s total_ms=%s",refresh_id,status,sources_successful,sources_seen,index.get("articles_new",0),phases["worker_total_ms"])
            return dict(self.repo.db.execute("SELECT * FROM content_ingestion_runs WHERE id=?",(refresh_id,)).fetchone())
        except Exception as exc:
            self.repo.db.execute("UPDATE content_ingestion_runs SET status='FAILED',completed_at=?,errors_json=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(),json.dumps({"error":str(exc)[:500],"worker_total_ms":int((time.monotonic()-total_started)*1000)},ensure_ascii=False),refresh_id))
            self.repo.db.commit(); raise


class BriefingGenerationWorker:
    def __init__(self, repo, generator=None, clock=None, max_attempts=None, timeout_minutes=None, worker_id=None, audio_service=None):
        self.repo=repo; ensure_phase42_schema(repo); self.generator=generator or EngineBriefingGenerator(repo); self.clock=clock or Clock(); self.max_attempts=int(max_attempts if max_attempts is not None else os.getenv("GENERATION_MAX_RETRIES",2)); self.timeout_minutes=int(timeout_minutes if timeout_minutes is not None else os.getenv("WORKER_JOB_TIMEOUT_MINUTES",30)); self.worker_id=worker_id or "worker_"+uuid.uuid4().hex; self.audio_service=audio_service
    def recover_stale(self):
        cutoff=(datetime.now(timezone.utc)-timedelta(minutes=self.timeout_minutes)).isoformat(); now=datetime.now(timezone.utc).isoformat()
        cur=self.repo.db.execute("""UPDATE generation_jobs SET status=CASE WHEN attempt_count<max_attempts THEN 'RETRY' ELSE 'FAILED' END,
            next_retry_at=CASE WHEN attempt_count<max_attempts THEN ? ELSE NULL END,finished_at=CASE WHEN attempt_count<max_attempts THEN NULL ELSE ? END,
            error_code='WORKER_TIMEOUT',error_message='stale RUNNING job recovered',worker_id=NULL WHERE status='RUNNING' AND started_at<?""",(now,now,cutoff)); self.repo.db.commit(); return cur.rowcount
    def claim(self):
        self.recover_stale()
        try:
            self.repo.db.execute("BEGIN IMMEDIATE")
            row=self.repo.db.execute("""SELECT * FROM generation_jobs j WHERE status IN ('PENDING','RETRY')
                AND (next_retry_at IS NULL OR next_retry_at<=?)
                AND NOT EXISTS (SELECT 1 FROM generation_jobs running WHERE running.profile_key=j.profile_key
                    AND running.briefing_date=j.briefing_date AND running.status='RUNNING')
                ORDER BY scheduled_for LIMIT 1""",(datetime.now(timezone.utc).isoformat(),)).fetchone()
            if not row: self.repo.db.rollback(); return None
            cur=self.repo.db.execute("UPDATE generation_jobs SET status='RUNNING',started_at=?,attempt_count=attempt_count+1,worker_id=? WHERE id=? AND status IN ('PENDING','RETRY')",(datetime.now(timezone.utc).isoformat(),self.worker_id,row["id"]));
            if cur.rowcount != 1: self.repo.db.rollback(); return None
            self.repo.db.commit(); return dict(self.repo.db.execute("SELECT * FROM generation_jobs WHERE id=?",(row["id"],)).fetchone())
        except Exception: self.repo.db.rollback(); raise

    def _refresh_content_index(self):
        """Run due content refreshes without coupling generation to a per-user action."""
        return NewsRefreshWorker(self.repo).refresh_if_due()

    def _claim_manual_refresh(self):
        ensure_phase42_schema(self.repo)
        try:
            self.repo.db.execute("BEGIN IMMEDIATE")
            row=self.repo.db.execute("SELECT * FROM manual_refresh_requests WHERE status='PENDING' ORDER BY requested_at LIMIT 1").fetchone()
            if not row:
                self.repo.db.rollback(); return None
            now=datetime.now(timezone.utc).isoformat()
            self.repo.db.execute("UPDATE manual_refresh_requests SET status='GENERATING',stage='INGESTION',started_at=?,updated_at=? WHERE id=? AND status='PENDING'",(now,now,row['id']))
            self.repo.db.commit()
            return dict(self.repo.db.execute("SELECT * FROM manual_refresh_requests WHERE id=?",(row['id'],)).fetchone())
        except Exception:
            self.repo.db.rollback(); raise

    def _run_manual_refresh(self, request):
        request_id=request['id']; now=datetime.now(timezone.utc).isoformat()
        try:
            prefs=self.repo.get_preferences(request['user_id'])
            if not prefs or (prefs.get('content_scope', 'selected') != 'all' and not prefs.get('topics')):
                raise GenerationError('PREFERENCES_INCOMPLETE','briefing preferences are unavailable')
            profile=BriefingProfile.from_preferences(prefs)
            ingestion=self._refresh_content_index(); ingestion_id=ingestion['id']
            self.repo.db.execute("UPDATE manual_refresh_requests SET ingestion_run_id=?,stage='COMPOSITION',updated_at=? WHERE id=?",(ingestion_id,datetime.now(timezone.utc).isoformat(),request_id)); self.repo.db.commit()
            from .content import compose
            local_date=datetime.now(ZoneInfo(prefs['timezone'])).date().isoformat()
            payload=compose(self.repo,profile.topics,profile.language,profile.briefing_size,profile.country_scope)
            if not payload.get('items'):
                raise GenerationError('NO_ELIGIBLE_CONTENT','fresh ingestion produced no eligible briefing items')
            edition_profile=profile.key()+'_manual_'+request_id
            edition_id,_=self._persist_edition({'briefing_date':local_date},profile,payload,edition_profile_key=edition_profile,generation_reason='MANUAL_REFRESH',ingestion_run_id=ingestion_id,generation_id=request_id)
            voice=self.audio_service.effective_voice(prefs.get('audio_voice_id'),profile.language) if self.audio_service and self.repo.config.audio_enabled else None
            self.repo.db.execute("UPDATE manual_refresh_requests SET edition_id=?,selected_voice_id=?,stage=?,status=?,updated_at=? WHERE id=?",
                (edition_id,voice,'AUDIO_QUEUED' if voice else 'CONTENT_READY','GENERATING' if voice else 'FAILED',datetime.now(timezone.utc).isoformat(),request_id)); self.repo.db.commit()
            if voice:
                audio_result=self.audio_service.request(edition_id,profile.language,voice)
                audio_job=self.repo.db.execute("SELECT id FROM audio_generation_jobs WHERE edition_id=? AND language=? AND voice=? ORDER BY created_at DESC LIMIT 1",(edition_id,profile.language,voice)).fetchone()
                self.repo.db.execute("UPDATE manual_refresh_requests SET audio_job_id=?,stage='AUDIO_QUEUED',updated_at=? WHERE id=?",(audio_job['id'] if audio_job else None,datetime.now(timezone.utc).isoformat(),request_id)); self.repo.db.commit()
                if audio_result.get('status')=='READY': self._publish_manual_refreshes()
            return {'worker_run_id':'worker_'+uuid.uuid4().hex,'jobs_claimed':1,'jobs_completed':1,'jobs_retried':0,'jobs_failed':0,'edition_generation_count':1,'users_served_by_edition':1,'manual_generation_id':request_id,'edition_id':edition_id}
        except Exception as exc:
            if isinstance(exc,sqlite3.IntegrityError) and self.repo.db.execute("SELECT 1 FROM content_ingestion_runs WHERE status='RUNNING' LIMIT 1").fetchone():
                self.repo.db.execute("UPDATE manual_refresh_requests SET status='PENDING',stage='WAITING_INGESTION',updated_at=? WHERE id=?",(datetime.now(timezone.utc).isoformat(),request_id)); self.repo.db.commit()
                return {'worker_run_id':'worker_'+uuid.uuid4().hex,'jobs_claimed':0,'jobs_completed':0,'jobs_retried':0,'jobs_failed':0,'edition_generation_count':0,'users_served_by_edition':0,'manual_generation_id':request_id,'waiting_for_shared_ingestion':True}
            code=exc.code if isinstance(exc,GenerationError) else 'MANUAL_REFRESH_FAILED'
            if 'ingestion_id' in locals():
                self.repo.db.execute("UPDATE content_ingestion_runs SET status='FAILED',completed_at=?,errors_json=? WHERE id=? AND status='RUNNING'",(datetime.now(timezone.utc).isoformat(),json.dumps({"error_code":code,"message":str(exc)[:500]}),ingestion_id))
            self.repo.db.execute("UPDATE manual_refresh_requests SET status='FAILED',stage='FAILED_FINAL',error_code=?,error_message=?,updated_at=?,finished_at=? WHERE id=?",
                (code,str(exc)[:500],datetime.now(timezone.utc).isoformat(),datetime.now(timezone.utc).isoformat(),request_id)); self.repo.db.commit()
            return {'worker_run_id':'worker_'+uuid.uuid4().hex,'jobs_claimed':1,'jobs_completed':0,'jobs_retried':0,'jobs_failed':1,'edition_generation_count':0,'users_served_by_edition':0,'manual_generation_id':request_id,'error_code':code}

    def _publish_manual_refreshes(self):
        if not self.audio_service: return
        rows=self.repo.db.execute("SELECT * FROM manual_refresh_requests WHERE status='GENERATING' AND edition_id IS NOT NULL AND stage IN ('AUDIO_QUEUED','AUDIO')").fetchall()
        for row in rows:
            metadata=self.audio_service.audio_for_edition(row['edition_id'],voice=row['selected_voice_id'])
            now=datetime.now(timezone.utc).isoformat()
            if metadata.get('status')=='READY' and metadata.get('artifact_id'):
                prefs=self.repo.get_preferences(row['user_id']); local_date=datetime.now(ZoneInfo(prefs['timezone'])).date().isoformat()
                delivery=self.repo.db.execute("SELECT id FROM user_briefing_deliveries WHERE user_id=? AND local_date=?",(row['user_id'],local_date)).fetchone()
                values=(row['edition_id'],row['selected_voice_id'],metadata['artifact_id'],metadata['script_id'],now)
                if delivery:
                    self.repo.db.execute("UPDATE user_briefing_deliveries SET edition_id=?,status='READY',audio_status='READY',selected_voice_id=?,active_voice_id=?,audio_artifact_id=?,script_id=?,generation_stage='READY',generation_updated_at=?,generation_error_code=NULL,generation_error_message=NULL,delivered_at=? WHERE id=?",
                        (row['edition_id'],row['selected_voice_id'],row['selected_voice_id'],metadata['artifact_id'],metadata['script_id'],now,now,delivery['id']))
                else:
                    self.repo.db.execute("INSERT INTO user_briefing_deliveries(id,user_id,edition_id,local_date,delivery_time,timezone,status,created_at,delivered_at,selected_voice_id,active_voice_id,audio_artifact_id,audio_status,generation_stage,generation_started_at,generation_updated_at,script_id) VALUES(?,?,?,?,?,?,'READY',?,?,?,?,?,'READY','READY',?,?,?)",
                        ('delivery_'+uuid.uuid4().hex,row['user_id'],row['edition_id'],local_date,prefs['briefing_time'],prefs['timezone'],now,now,row['selected_voice_id'],row['selected_voice_id'],metadata['artifact_id'],now,now,metadata['script_id']))
                self.repo.db.execute("UPDATE manual_refresh_requests SET status='READY',stage='READY',audio_variant_id=?,updated_at=?,finished_at=?,error_code=NULL,error_message=NULL WHERE id=?",(metadata['artifact_id'],now,now,row['id']))
            elif metadata.get('status')=='FAILED':
                self.repo.db.execute("UPDATE manual_refresh_requests SET status='FAILED',stage='FAILED_FINAL',error_code=?,error_message=?,updated_at=?,finished_at=? WHERE id=?",(metadata.get('error_code') or 'TTS_FAILED','Audio generation failed; consult audio diagnostics.',now,now,row['id']))
        self.repo.db.commit()
    def _persist_edition(self, job, profile, payload, edition_profile_key=None, generation_reason='SCHEDULED', ingestion_run_id=None, generation_id=None):
        edition_profile_key=edition_profile_key or profile.key()
        existing=self.repo.db.execute("SELECT * FROM briefing_editions WHERE profile_key=? AND edition_date=?",(edition_profile_key,job["briefing_date"])).fetchone()
        if existing and existing["status"]=="READY": return existing["id"],False
        eid=existing["id"] if existing else "edition_"+uuid.uuid4().hex; t=datetime.now(timezone.utc).isoformat(); items=payload.get("items",[]); status="READY" if len(items)>=MINIMUM_DELIVERABLE_ITEMS else ("PARTIAL" if items else "FAILED"); self.repo.db.execute("INSERT OR REPLACE INTO briefing_editions VALUES(?,?,?,?,?,?,?,?,?)",(eid,edition_profile_key,job["briefing_date"],profile.language,status,payload.get("generated_at",t),len(items),payload.get("engine_version","phase_4.2"),t)); self.repo.db.execute("DELETE FROM briefing_edition_items WHERE edition_id=?",(eid,))
        for pos,item in enumerate(items,1):
            warnings=list(item.get("warnings",[])); warnings.append("__summary_provider__:"+item.get("summary_provider",item.get("provenance",{}).get("summary_provider","ollama")))
            self.repo.db.execute("""INSERT INTO briefing_edition_items
                (id,edition_id,position,event_id,headline,summary,why_it_matters,key_points_json,
                 confidence,evidence_quality,trace_id,warnings_json,sources_json,created_at,
                 primary_taxonomy_id,primary_taxonomy_label,primary_taxonomy_reason,
                 matched_taxonomy_ids_json,user_interest_matches_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("edition_item_"+uuid.uuid4().hex,eid,pos,item.get("event_id"),item.get("headline"),item.get("summary"),item.get("why_it_matters"),json.dumps(item.get("key_points",[]),ensure_ascii=False),item.get("confidence"),item.get("evidence_quality"),item.get("provenance",{}).get("trace_id"),json.dumps(warnings,ensure_ascii=False),json.dumps(item.get("sources",[]),ensure_ascii=False),t,
                 item.get("primary_taxonomy_id"),item.get("primary_taxonomy_label"),item.get("primary_taxonomy_reason"),
                 json.dumps(item.get("matched_taxonomy_ids",[]),ensure_ascii=False),
                 json.dumps(item.get("user_interest_matches",[]),ensure_ascii=False)))
        return eid,True
    def run_once(self):
        manual=self._claim_manual_refresh()
        if manual:
            return self._run_manual_refresh(manual)
        run_id="worker_"+uuid.uuid4().hex; job=self.claim(); result={"worker_run_id":run_id,"jobs_claimed":1 if job else 0,"jobs_completed":0,"jobs_retried":0,"jobs_failed":0,"edition_generation_count":0,"users_served_by_edition":0}
        if not job: return result
        total_started=time.monotonic()
        try:
            prefs=self.repo.get_preferences(job["user_id"]); profile=BriefingProfile.from_preferences(prefs); existing=self.repo.db.execute("SELECT id FROM briefing_editions WHERE profile_key=? AND edition_date=? AND status='READY'",(profile.key(),job["briefing_date"])).fetchone()
            if existing: eid=existing["id"]; generated=False
            else:
                compose_started=time.monotonic()
                refresh_started=time.monotonic()
                if isinstance(self.generator,EngineBriefingGenerator):
                    self._refresh_content_index()
                    self.generator.last_phase_durations['CONTENT_REFRESH']=int((time.monotonic()-refresh_started)*1000)
                payload=self.generator.generate(profile.topics,profile.language,profile.briefing_size,job["briefing_date"],profile.country_scope)
                for phase_name,duration in getattr(self.generator,"last_phase_durations",{}).items():
                    self.repo.db.execute("INSERT OR REPLACE INTO generation_job_phases(job_id,phase,duration_ms,recorded_at) VALUES(?,?,?,?)",(job["id"],phase_name,int(duration),datetime.now(timezone.utc).isoformat()))
                self.repo.db.commit()
                if not payload.get("items"):
                    from .content import compose, ensure_content_schema
                    ensure_content_schema(self.repo)
                    if self.repo.db.execute("SELECT 1 FROM indexed_content LIMIT 1").fetchone():
                        fallback=compose(self.repo,profile.topics,profile.language,profile.briefing_size,profile.country_scope)
                        if fallback.get("items"): payload=fallback
                eid,generated=self._persist_edition(job,profile,payload)
                self.repo.db.execute("INSERT OR REPLACE INTO generation_job_phases(job_id,phase,duration_ms,recorded_at) VALUES(?,?,?,?)",(job["id"],"EDITION_PERSISTENCE",int((time.monotonic()-compose_started)*1000),datetime.now(timezone.utc).isoformat())); self.repo.db.commit()
            edition=self.repo.db.execute("SELECT status,item_count FROM briefing_editions WHERE id=?",(eid,)).fetchone()
            if not edition or edition["status"]!="READY" or int(edition["item_count"] or 0)<MINIMUM_DELIVERABLE_ITEMS:
                raise GenerationError("NO_DELIVERABLE_ITEMS","edition has no deliverable items")
            t=datetime.now(timezone.utc).isoformat(); delivery=self.repo.db.execute("SELECT id FROM user_briefing_deliveries WHERE user_id=? AND local_date=?",(job["user_id"],job["briefing_date"])).fetchone()
            delivery_id=delivery["id"] if delivery else "delivery_"+uuid.uuid4().hex
            self.repo.db.execute("""INSERT INTO user_briefing_deliveries
                (id,user_id,edition_id,local_date,delivery_time,timezone,status,created_at,delivered_at,
                 selected_voice_id,active_voice_id,audio_artifact_id,audio_status,generation_stage,
                 generation_started_at,generation_updated_at,generation_error_code,generation_error_message,script_id)
                VALUES(?,?,?,?,?,?,?, ?,NULL,?,NULL,NULL,'PENDING','AUDIO_QUEUED',?,?,NULL,NULL,NULL)
                ON CONFLICT(user_id,local_date) DO UPDATE SET edition_id=excluded.edition_id,status='AUDIO_QUEUED',
                selected_voice_id=excluded.selected_voice_id,audio_status='PENDING',generation_stage='AUDIO_QUEUED',
                generation_started_at=COALESCE(user_briefing_deliveries.generation_started_at,excluded.generation_started_at),
                generation_updated_at=excluded.generation_updated_at,generation_error_code=NULL,generation_error_message=NULL""",
                (delivery_id,job["user_id"],eid,job["briefing_date"],job["delivery_time"],job["timezone"],"AUDIO_QUEUED",t,prefs.get("audio_voice_id"),t,t))
            self.repo.db.execute("UPDATE generation_jobs SET status='COMPLETED',finished_at=?,error_code=NULL,error_message=NULL WHERE id=?",(t,job["id"])); self.repo.db.commit()
            scheduled=datetime.fromisoformat(job["scheduled_for"])
            queue_ms=max(0,int((datetime.now(timezone.utc)-scheduled.astimezone(timezone.utc)).total_seconds()*1000))
            self.repo.db.execute("INSERT OR REPLACE INTO generation_job_phases(job_id,phase,duration_ms,recorded_at) VALUES(?,?,?,?)",(job["id"],"QUEUE_WAIT",queue_ms,t))
            self.repo.db.execute("INSERT OR REPLACE INTO generation_job_phases(job_id,phase,duration_ms,recorded_at) VALUES(?,?,?,?)",(job["id"],"TOTAL_DELIVERY_CONTENT",int((time.monotonic()-total_started)*1000),t)); self.repo.db.commit()
            if self.repo.config.audio_enabled:
                try:
                    from .audio import AudioService
                    voice=self.repo.get_preferences(job["user_id"]).get("audio_voice_id")
                    audio=self.audio_service or AudioService(self.repo)
                    queued=audio.request(eid, profile.language, voice)
                    audio.attach_variant_to_delivery(delivery_id, queued)
                except Exception as exc:
                    import logging
                    self.repo.db.execute("UPDATE user_briefing_deliveries SET audio_status='FAILED',generation_stage='FAILED_FINAL',generation_error_code='AUDIO_ENQUEUE_FAILED',generation_error_message=?,generation_updated_at=? WHERE id=?",(str(exc)[:500],datetime.now(timezone.utc).isoformat(),delivery_id)); self.repo.db.commit()
                    logging.getLogger(__name__).exception("audio enqueue failed for edition %s", eid)
            else:
                self.repo.db.execute("UPDATE user_briefing_deliveries SET status='CONTENT_READY',audio_status='NOT_AVAILABLE',generation_stage='CONTENT_READY',generation_updated_at=? WHERE id=?",(t,delivery_id)); self.repo.db.commit()
            from .notifications import NotificationService
            NotificationService(self.repo).enqueue_ready()
            result["jobs_completed"]=1; result["edition_generation_count"]=1 if generated else 0; result["users_served_by_edition"]=1; return result
        except GenerationError as exc: return self._failure(job,exc.code,str(exc),result)
        except Exception as exc: return self._failure(job,"ENGINE_FAILED",str(exc),result)
    def _failure(self,job,code,message,result):
        retry=job["attempt_count"] < job["max_attempts"]; status="RETRY" if retry else "FAILED"; next_at=(datetime.now(timezone.utc)+timedelta(minutes=2**job["attempt_count"])).isoformat() if retry else None; self.repo.db.execute("UPDATE generation_jobs SET status=?,finished_at=?,next_retry_at=?,error_code=?,error_message=? WHERE id=?",(status,datetime.now(timezone.utc).isoformat(),next_at,code,message,job["id"])); self.repo.db.commit(); result["jobs_retried" if retry else "jobs_failed"]+=1; return result

    def run_batch(self, batch_size=None):
        size = max(1, int(batch_size or os.getenv("WORKER_BATCH_SIZE", "20")))
        result = {"jobs_claimed": 0, "jobs_completed": 0, "jobs_retried": 0, "jobs_failed": 0,
                  "edition_generation_count": 0, "users_served_by_edition": 0}
        for _ in range(size):
            current = self.run_once()
            for key in result: result[key] += current.get(key, 0)
            if not current["jobs_claimed"]: break
        return result

    def run_forever(self, interval_seconds=None, batch_size=None):
        interval = max(1.0, float(interval_seconds or os.getenv("WORKER_POLL_SECONDS", "15")))
        try:
            while True:
                self.run_batch(batch_size)
                time.sleep(interval)
        except KeyboardInterrupt:
            return


class BriefingDeliveryWorker:
    """One continuous owner for scheduler, edition, audio validation and notification handoff."""
    def __init__(self, repo, generator=None, interval_seconds=None, batch_size=None):
        from .audio import AudioService
        from .notifications import NotificationService
        self.repo=repo
        self.scheduler=BriefingScheduler(repo)
        self.audio=AudioService(repo)
        self.generation=BriefingGenerationWorker(repo,generator=generator,audio_service=self.audio)
        self.news_refresh=NewsRefreshWorker(repo)
        self.notifications=NotificationService(repo)
        self.interval_seconds=max(1.0,float(interval_seconds or os.getenv("DELIVERY_WORKER_POLL_SECONDS","15")))
        self.batch_size=max(1,int(batch_size or os.getenv("WORKER_BATCH_SIZE","20")))

    def run_once(self):
        scheduled=self.scheduler.run_once()
        generated=self.generation.run_batch(self.batch_size)
        variants_enqueued=self.audio.enqueue_ready_editions()
        audio=self.audio.generate_pending()
        try:
            refresh=self.news_refresh.refresh_if_due()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("periodic news refresh failed; previous indexed content remains available")
            refresh={"status":"FAILED","error":str(exc)[:200]}
        self.generation._publish_manual_refreshes()
        notifications=self.notifications.enqueue_ready()
        notification=self.notifications.run_once()
        return {"scheduled":scheduled,"generation":generated,"news_refresh":refresh,"audio_jobs_enqueued":variants_enqueued,
            "audio":audio,"notifications_enqueued":notifications,"notification_delivery":notification}

    def run_forever(self):
        import logging
        try:
            while True:
                try: self.run_once()
                except Exception: logging.getLogger(__name__).exception("briefing delivery worker cycle failed")
                time.sleep(self.interval_seconds)
        except KeyboardInterrupt:
            return


def serialize_edition(repo, edition_id):
    row=repo.db.execute("SELECT * FROM briefing_editions WHERE id=?",(edition_id,)).fetchone();
    if not row: return None
    image_by_article={}
    indexed=repo.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='indexed_content'").fetchone()
    indexed_columns={column[1] for column in repo.db.execute("PRAGMA table_info(indexed_content)")} if indexed else set()
    if "image_url" in indexed_columns:
        article_ids=[]
        for stored in repo.db.execute("SELECT sources_json FROM briefing_edition_items WHERE edition_id=?",(edition_id,)):
            for source in json.loads(stored["sources_json"] or "[]"):
                article_id=(source.get("article_id") or source.get("id")) if isinstance(source,dict) else None
                if article_id: article_ids.append(article_id)
        if article_ids:
            article_ids=sorted(set(article_ids))
            marks=",".join("?" for _ in article_ids)
            image_by_article={item["id"]:item["image_url"] for item in repo.db.execute("SELECT id,image_url FROM indexed_content WHERE id IN ("+marks+")",tuple(article_ids))}
    out=dict(row); out["items"]=[]
    for item in repo.db.execute("SELECT * FROM briefing_edition_items WHERE edition_id=? ORDER BY position",(edition_id,)):
        x=dict(item); x["key_points"]=json.loads(x.pop("key_points_json")); warnings=json.loads(x.pop("warnings_json")); marker=next((w for w in warnings if isinstance(w,str) and w.startswith("__summary_provider__:")),"__summary_provider__:ollama"); x["summary_provider"]=marker.split(":",1)[1]; x["warnings"]=[w for w in warnings if w!=marker]; x["sources"]=json.loads(x.pop("sources_json")); x.pop("edition_id",None); x.pop("created_at",None)
        has_indexed_sources=False
        for source in x["sources"]:
            if not isinstance(source,dict): continue
            article_id=source.get("article_id") or source.get("id")
            if article_id and "image_url" in indexed_columns:
                has_indexed_sources=True
                source["image_url"]=image_by_article.get(article_id)
        canonical_source_image=next((source.get("image_url") for source in x["sources"] if isinstance(source,dict) and source.get("image_url")),None)
        x["image_url"]=canonical_source_image if has_indexed_sources else (x.get("image_url") or canonical_source_image)
        x.pop("primary_taxonomy_reason",None); x.pop("matched_taxonomy_ids_json",None); x.pop("user_interest_matches_json",None)
        out["items"].append(x)
    return out


def briefing_health(repo, stale_minutes=30):
    """Aggregate pipeline status without returning user identifiers or credentials."""
    ensure_phase42_schema(repo)
    from .audio import ensure_audio_schema
    ensure_audio_schema(repo)
    now=datetime.now(timezone.utc); cutoff=(now-timedelta(minutes=stale_minutes)).isoformat()
    generation={row["status"]:row["count"] for row in repo.db.execute("SELECT status,COUNT(*) AS count FROM generation_jobs GROUP BY status")}
    audio={row["status"]:row["count"] for row in repo.db.execute("SELECT status,COUNT(*) AS count FROM audio_generation_jobs GROUP BY status")}
    deliveries={row["status"]:row["count"] for row in repo.db.execute("SELECT status,COUNT(*) AS count FROM user_briefing_deliveries GROUP BY status")}
    oldest=repo.db.execute("SELECT MIN(created_at) AS created_at FROM audio_generation_jobs WHERE status IN ('PENDING','GENERATING')").fetchone()["created_at"]
    gen_averages={row["phase"]:round(row["avg_ms"]) for row in repo.db.execute("SELECT phase,AVG(duration_ms) AS avg_ms FROM generation_job_phases GROUP BY phase")}
    audio_averages={row["phase"]:round(row["avg_ms"]) for row in repo.db.execute("SELECT phase,AVG(duration_ms) AS avg_ms FROM audio_job_phases GROUP BY phase")}
    manual={row["status"]:row["count"] for row in repo.db.execute("SELECT status,COUNT(*) AS count FROM manual_refresh_requests GROUP BY status")}
    ingestion=repo.db.execute("SELECT id,status,started_at,completed_at,sources_attempted,sources_successful,articles_seen,articles_new,articles_updated,articles_unchanged,errors_json,source_metrics_json FROM content_ingestion_runs ORDER BY started_at DESC LIMIT 1").fetchone()
    ready=repo.db.execute("""SELECT COUNT(*) FROM user_briefing_deliveries d JOIN audio_artifacts a ON a.id=d.audio_artifact_id
        WHERE d.status='READY' AND d.audio_status='READY' AND d.active_voice_id=d.selected_voice_id
        AND a.status='READY' AND a.duration_ms>0 AND a.size_bytes>=128""").fetchone()[0]
    queued=sum(audio.get(key,0) for key in ("PENDING",))
    running=audio.get("GENERATING",0)
    stale=repo.db.execute("SELECT COUNT(*) FROM audio_generation_jobs WHERE status='GENERATING' AND COALESCE(updated_at,started_at)<?",(cutoff,)).fetchone()[0]
    return {"as_of":now.isoformat(),"generation_jobs":generation,"audio_jobs":audio,"deliveries":deliveries,
        "audio_queued":queued,"audio_running":running,"audio_stale":stale,"audio_failed":audio.get("FAILED",0),
        "audio_ready":audio.get("READY",0),"ready_deliveries":ready,"oldest_pending_audio_job":oldest,
        "generation_phase_avg_ms":gen_averages,"audio_phase_avg_ms":audio_averages,
        "manual_generations":manual,"latest_ingestion":({**dict(ingestion),"errors_json":json.loads(ingestion["errors_json"] or "{}"),"source_metrics":json.loads(ingestion["source_metrics_json"] or "[]")} if ingestion else None)}


def briefing_diagnostic(repo, identifier):
    ensure_phase42_schema(repo)
    from .audio import ensure_audio_schema
    ensure_audio_schema(repo)
    manual=repo.db.execute("SELECT * FROM manual_refresh_requests WHERE id=?",(identifier,)).fetchone()
    if manual:
        ingestion=repo.db.execute("SELECT * FROM content_ingestion_runs WHERE id=?",(manual["ingestion_run_id"],)).fetchone() if manual["ingestion_run_id"] else None
        edition=repo.db.execute("SELECT id,edition_date,status,generated_at,item_count,engine_version FROM briefing_editions WHERE id=?",(manual["edition_id"],)).fetchone() if manual["edition_id"] else None
        audio_job=repo.db.execute("SELECT * FROM audio_generation_jobs WHERE id=?",(manual["audio_job_id"],)).fetchone() if manual["audio_job_id"] else None
        artifact=repo.db.execute("SELECT id,status,provider,voice,language,mime_type,storage_path,duration_ms,size_bytes,checksum,created_at FROM audio_artifacts WHERE id=?",(manual["audio_variant_id"],)).fetchone() if manual["audio_variant_id"] else None
        return {"found":True,"manual_generation":{k:manual[k] for k in ("id","reason","status","stage","requested_at","started_at","updated_at","finished_at","ingestion_run_id","edition_id","audio_job_id","selected_voice_id","audio_variant_id","error_code","error_message")},"ingestion_run":({**dict(ingestion),"errors":json.loads(ingestion["errors_json"] or "{}")} if ingestion else None),"edition":dict(edition) if edition else None,"audio_job":dict(audio_job) if audio_job else None,"audio_artifact":dict(artifact) if artifact else None}
    delivery=repo.db.execute("SELECT * FROM user_briefing_deliveries WHERE id=? OR user_id=? ORDER BY local_date DESC LIMIT 1",(identifier,identifier)).fetchone()
    if not delivery: return {"found":False}
    generation=repo.db.execute("SELECT id,status,attempt_count,max_attempts,scheduled_for,started_at,finished_at,error_code,error_message,profile_key FROM generation_jobs WHERE user_id=? AND briefing_date=?",(delivery["user_id"],delivery["local_date"])).fetchone()
    audio_job=repo.db.execute("SELECT * FROM audio_generation_jobs WHERE edition_id=? ORDER BY created_at DESC LIMIT 1",(delivery["edition_id"],)).fetchone()
    artifact=repo.db.execute("SELECT id,status,provider,voice,language,mime_type,storage_path,duration_ms,size_bytes,checksum,created_at FROM audio_artifacts WHERE id=?",(delivery["audio_artifact_id"],)).fetchone() if delivery["audio_artifact_id"] else None
    gen_phases=list(repo.db.execute("SELECT phase,duration_ms,recorded_at FROM generation_job_phases WHERE job_id=? ORDER BY id",(generation["id"],))) if generation else []
    audio_phases=list(repo.db.execute("SELECT phase,duration_ms,started_at,finished_at,status,error_code FROM audio_job_phases WHERE audio_job_id=? ORDER BY id",(audio_job["id"],))) if audio_job else []
    return {"found":True,"delivery":{"id":delivery["id"],"edition_id":delivery["edition_id"],"date":delivery["local_date"],"status":delivery["status"],"audio_status":delivery["audio_status"],"stage":delivery["generation_stage"],"selected_voice_id":delivery["selected_voice_id"],"active_voice_id":delivery["active_voice_id"],"script_id":delivery["script_id"],"audio_artifact_id":delivery["audio_artifact_id"],"started_at":delivery["generation_started_at"],"updated_at":delivery["generation_updated_at"],"error_code":delivery["generation_error_code"],"error_message":delivery["generation_error_message"]},"generation_job":dict(generation) if generation else None,"audio_job":dict(audio_job) if audio_job else None,"audio_artifact":dict(artifact) if artifact else None,"generation_phases":[dict(x) for x in gen_phases],"audio_phases":[dict(x) for x in audio_phases]}

