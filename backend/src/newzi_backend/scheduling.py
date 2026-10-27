"""Phase 4.2 scheduling, shared editions and asynchronous generation worker."""
import hashlib, json, os, uuid
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from newzi_engine.paths import ENGINE_ROOT
from newzi_engine.topic_registry import taxonomy

from . import db as database
from .timeutil import iso, now_iso, parse

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
    narration: str = "standard"
    def key(self):
        raw={"profile_schema_version":PROFILE_SCHEMA_VERSION,"topics":taxonomy().canonicalize(self.topics)[0],"language":self.language,"briefing_size":self.briefing_size,"country_scope":self.country_scope}
        # Only the extended narration is part of the key: standard profiles keep the keys they always had.
        if self.narration!="standard": raw["narration"]=self.narration
        return "profile_"+hashlib.sha256(json.dumps(raw,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
    @classmethod
    def from_preferences(cls, prefs, narration=None):
        # Following everything means every domain: composition then gives each one a slot, instead of
        # filling the briefing with whichever few domains publish the most.
        topics = tuple(taxonomy().roots()) if prefs.get("content_scope") == "all" else taxonomy().canonicalize(prefs["topics"])[0]
        return cls(topics,prefs["language"],int(prefs["briefing_size"]),prefs["country_scope"],narration or "standard")
    @classmethod
    def for_slot(cls, prefs, slot):
        """The profile of one of the day's briefings (see briefing_slots): its theme and its length."""
        from .briefing_slots import slot_preferences
        return cls.from_preferences(slot_preferences(prefs, slot), (slot or {}).get("length"))


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


def _elapsed_ms(started, finished):
    """Milliseconds between two stored ISO-8601 timestamps (None when unparsable)."""
    try:
        return (parse(finished) - parse(started)).total_seconds() * 1000
    except (AttributeError, TypeError, ValueError):
        return None


def user_edition_key(profile, user_id, slot=1):
    """Edition key of one user's scheduled briefing: the profile says what to select, the user owns the edition."""
    return profile.key()+"_user_"+user_id+("" if slot==1 else f"_slot{slot}")


class FixtureBriefingGenerator:
    def __init__(self,path=None): self.path=Path(path or (ENGINE_ROOT / "fixtures" / "briefing.json")); self.calls=0
    def generate(self, topics, language, briefing_size, date, country_scope="BOTH", user_id=None, tz=None, since_today=False):
        self.calls+=1
        data=json.loads(self.path.read_text(encoding="utf-8")); items=data.get("items",[])[:briefing_size]
        return {"status":"READY" if items else "PARTIAL","generated_at":data.get("generated_at"),"engine_version":"phase_3.3-fixture","items":items}


class EngineBriefingGenerator:
    def __init__(self, repo=None): self.calls=0; self.repo=repo; self.last_sync=None; self.sync_metrics={}; self.last_phase_durations={}
    def generate(self, topics, language, briefing_size, date, country_scope="BOTH", user_id=None, tz=None, since_today=False):
        self.calls+=1
        try:
            from .content import compose
            if self.repo is None: raise GenerationError("CONFIG_ERROR", "content repository unavailable")
            now=datetime.now(timezone.utc)
            self.last_phase_durations.setdefault("CONTENT_REFRESH",0)
            phase=time.monotonic(); result=compose(self.repo,topics,language,briefing_size,country_scope,now,briefing_date=date,user_id=user_id,tz=tz,since_today=since_today)
            self.last_phase_durations["CONTENT_COMPOSITION"]=int((time.monotonic()-phase)*1000)
            return result
        except GenerationError: raise
        except Exception as exc: raise GenerationError("ENGINE_FAILED",str(exc))


class BriefingScheduler:
    def __init__(self, repo, clock=None, lead_minutes=None, max_attempts=None):
        self.repo=repo; self.clock=clock or Clock(); self._lead_override=lead_minutes if lead_minutes is not None else os.getenv("BRIEFING_GENERATION_LEAD_MINUTES"); self.lead_minutes=int(self._lead_override) if self._lead_override is not None else self._measured_lead_minutes(); self.max_attempts=int(max_attempts if max_attempts is not None else os.getenv("GENERATION_MAX_RETRIES",2)); self._lead_measured_at=time.monotonic()
    @staticmethod
    def _p95(values):
        numbers=sorted(int(value or 0) for value in values if value is not None and int(value or 0)>0)
        return numbers[min(len(numbers)-1, max(0, int(len(numbers)*.95)-1))] if numbers else None
    def _measured_lead_minutes(self):
        fallback=max(1,int(os.getenv("BRIEFING_GENERATION_LEAD_FALLBACK_MINUTES","10")))
        safety=max(0,int(os.getenv("BRIEFING_GENERATION_SAFETY_MINUTES","2")))
        try:
            ingestion=[_elapsed_ms(r["started_at"],r["completed_at"]) for r in self.repo.db.execute("SELECT started_at,completed_at FROM content_ingestion_runs WHERE status='READY' AND completed_at IS NOT NULL ORDER BY started_at DESC LIMIT 100")]
            composition=[r[0] for r in self.repo.db.execute("SELECT duration_ms FROM generation_job_phases WHERE phase='TOTAL_DELIVERY_CONTENT' ORDER BY recorded_at DESC LIMIT 100")]
            audio=[r[0] for r in self.repo.db.execute("SELECT duration_ms FROM audio_job_phases WHERE phase IN ('TTS','VALIDATION','STORAGE') ORDER BY id DESC LIMIT 300")]
            p95=sum(x or 0 for x in (self._p95(ingestion),self._p95(composition),self._p95(audio)))
            if p95<=0: return fallback
            return max(1,min(180,(p95+59_999)//60_000+safety))
        except database.OperationalError:
            self.repo.db.rollback(); return fallback
    def _eligible(self,prefs, now, time=None):
        local=now.astimezone(ZoneInfo(prefs["timezone"])); delivery=datetime.combine(local.date(),datetime.strptime(time or prefs["briefing_time"],"%H:%M").time(),ZoneInfo(prefs["timezone"])); return local >= delivery-timedelta(minutes=self.lead_minutes), local.date().isoformat(), delivery
    def _current_lead_minutes(self):
        if self._lead_override is not None: return int(self._lead_override)
        # The p95 reads up to 500 timing rows; it changes slowly, so refresh it every few minutes.
        if self._lead_measured_at is None or time.monotonic()-self._lead_measured_at>300:
            self.lead_minutes=self._measured_lead_minutes(); self._lead_measured_at=time.monotonic()
        return self.lead_minutes
    def run_once(self):
        self.lead_minutes=self._current_lead_minutes()
        run_id="scheduler_"+uuid.uuid4().hex; discovered=created=skipped=0; now=self.clock.now("UTC")
        # One query for all preferences and one for today's existing jobs, instead of two per user.
        due=[]
        from .briefing_slots import scheduled_slots
        extra=self._extra_slots_by_user()
        for uid,prefs in self.repo.active_preferences():
            # The daily briefing, plus the extra ones of a Premium account (each at its own time).
            slots=scheduled_slots(self.repo,uid,prefs) if uid in extra else [{"slot":1,"time":prefs["briefing_time"],"theme":None,"length":prefs.get("briefing_length") or "standard"}]
            for slot in slots:
                eligible,local_date,delivery=self._eligible(prefs,now,slot["time"])
                if eligible: due.append((uid,prefs,local_date,delivery,slot))
        dates=sorted({item[2] for item in due})
        existing_jobs={}
        if dates:
            for job in self.repo.db.execute("SELECT id,user_id,briefing_date,profile_key,status,slot FROM generation_jobs WHERE briefing_date IN ("+",".join("?" for _ in dates)+")",dates):
                existing_jobs[(job["user_id"],job["briefing_date"],job["slot"])]=job
        for uid,prefs,local_date,delivery,slot in due:
            discovered+=1; existing=existing_jobs.get((uid,local_date,slot["slot"]))
            if slot["slot"]==1 and prefs.get("briefing_length")=="extended" and uid not in extra:
                slot={**slot,"length":"standard"}  # the extended briefing is Premium
            profile=BriefingProfile.for_slot(prefs,slot)
            if existing:
                if existing["profile_key"]!=profile.key() and existing["status"]!="RUNNING":
                    self.repo.db.executemany("INSERT INTO profile_taxonomy(profile_key,taxonomy_id) VALUES(?,?) ON CONFLICT DO NOTHING", [(profile.key(), topic) for topic in profile.topics])
                    self.repo.db.execute("UPDATE generation_jobs SET profile_key=?,status='PENDING',attempt_count=0,error_code=NULL,error_message=NULL,next_retry_at=NULL WHERE id=?",(profile.key(),existing["id"])); created+=1
                else: skipped+=1
                continue
            self.repo.db.executemany("INSERT INTO profile_taxonomy(profile_key,taxonomy_id) VALUES(?,?) ON CONFLICT DO NOTHING", [(profile.key(), topic) for topic in profile.topics])
            scheduled=iso(delivery-timedelta(minutes=self.lead_minutes)); self.repo.db.execute("INSERT INTO generation_jobs(id,user_id,briefing_date,scheduled_for,delivery_time,timezone,status,attempt_count,max_attempts,created_at,started_at,finished_at,next_retry_at,error_code,error_message,profile_key,worker_id,slot) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",("job_"+uuid.uuid4().hex,uid,local_date,scheduled,slot["time"],prefs["timezone"],"PENDING",0,self.max_attempts,now_iso(),None,None,None,None,None,profile.key(),None,slot["slot"])); created+=1
        self.repo.db.commit(); return {"scheduler_run_id":run_id,"jobs_discovered":discovered,"jobs_created":created,"jobs_skipped_existing":skipped,"lead_minutes":self.lead_minutes}

    def _extra_slots_by_user(self):
        """Accounts whose Premium features are open and that have extra briefings (one query, not one per user)."""
        from .subscriptions import has_premium_features, premium_enforced
        users={row["user_id"] for row in self.repo.db.execute("SELECT DISTINCT user_id FROM briefing_slots WHERE enabled=1")}
        if premium_enforced():
            users|={row["user_id"] for row in self.repo.db.execute("SELECT user_id FROM user_preferences WHERE briefing_length='extended'")}
            return {uid for uid in users if has_premium_features(self.repo,uid)}
        return users|{row["user_id"] for row in self.repo.db.execute("SELECT user_id FROM user_preferences WHERE briefing_length='extended'")}

    def schedule_user_now(self, user_id):
        """Idempotently schedule a first/current-day edition after onboarding or profile changes."""
        prefs=self.repo.get_preferences(user_id)
        if not prefs or (prefs.get("content_scope", "selected") != "all" and not prefs.get("topics")):
            return {"scheduled":False,"reason":"PREFERENCES_INCOMPLETE"}
        from .briefing_slots import slot_for
        profile=BriefingProfile.for_slot(prefs,slot_for(self.repo,user_id,1,prefs))
        local_now=self.clock.now("UTC").astimezone(ZoneInfo(prefs["timezone"]))
        local_date=local_now.date().isoformat()
        self.repo.db.executemany("INSERT INTO profile_taxonomy(profile_key,taxonomy_id) VALUES(?,?) ON CONFLICT DO NOTHING",[(profile.key(),topic) for topic in profile.topics])
        existing=self.repo.db.execute("SELECT id,profile_key,status FROM generation_jobs WHERE user_id=? AND briefing_date=? AND slot=1",(user_id,local_date)).fetchone()
        if existing:
            if existing["profile_key"]==profile.key() and existing["status"] in ("PENDING","RUNNING","COMPLETED"):
                self.repo.db.commit(); return {"scheduled":False,"reason":"ALREADY_SCHEDULED","job_id":existing["id"]}
            if existing["status"]=="RUNNING":
                self.repo.db.commit(); return {"scheduled":False,"reason":"ALREADY_RUNNING","job_id":existing["id"]}
            self.repo.db.execute("UPDATE generation_jobs SET profile_key=?,status='PENDING',attempt_count=0,scheduled_for=?,finished_at=NULL,next_retry_at=NULL,error_code=NULL,error_message=NULL WHERE id=?",(profile.key(),now_iso(),existing["id"]))
            self.repo.db.commit(); return {"scheduled":True,"job_id":existing["id"]}
        job_id="job_"+uuid.uuid4().hex
        self.repo.db.execute("INSERT INTO generation_jobs(id,user_id,briefing_date,scheduled_for,delivery_time,timezone,status,attempt_count,max_attempts,created_at,started_at,finished_at,next_retry_at,error_code,error_message,profile_key,worker_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(job_id,user_id,local_date,now_iso(),prefs["briefing_time"],prefs["timezone"],"PENDING",0,self.max_attempts,now_iso(),None,None,None,None,None,profile.key(),None))
        self.repo.db.commit(); return {"scheduled":True,"job_id":job_id}

    def regenerate_for_preferences(self, user_id):
        """Build a brand-new edition for today after a content-profile change.

        Never reuses an edition cached earlier today (it may predate new content or selection rules).
        The user's current briefing stays playable until the new audio is READY, then the delivery
        is swapped by the worker (see BriefingGenerationWorker._publish_manual_refreshes).
        """
        prefs=self.repo.get_preferences(user_id)
        if not prefs or (prefs.get("content_scope", "selected") != "all" and not prefs.get("topics")):
            return {"scheduled":False,"reason":"PREFERENCES_INCOMPLETE"}
        if not self.repo.config.audio_enabled:
            return self.schedule_user_now(user_id)
        from .briefing_slots import slot_for
        profile=BriefingProfile.for_slot(prefs,slot_for(self.repo,user_id,1,prefs))
        now=datetime.now(timezone.utc); stamp=iso(now)
        local_date=now.astimezone(ZoneInfo(prefs["timezone"])).date().isoformat()
        self.repo.db.executemany("INSERT INTO profile_taxonomy(profile_key,taxonomy_id) VALUES(?,?) ON CONFLICT DO NOTHING",[(profile.key(),topic) for topic in profile.topics])
        # Regenerations built from older preferences must not be published after this one.
        self.repo.db.execute("UPDATE manual_refresh_requests SET status='FAILED',stage='FAILED_FINAL',error_code='SUPERSEDED',error_message='superseded by newer preferences',updated_at=?,finished_at=? WHERE user_id=? AND status IN ('PENDING','GENERATING')",(stamp,stamp,user_id))
        # Today's scheduled job must not re-run with a cached edition and overwrite the regenerated one.
        job=self.repo.db.execute("SELECT id,status,scheduled_for FROM generation_jobs WHERE user_id=? AND briefing_date=? AND slot=1",(user_id,local_date)).fetchone()
        if job and job["status"]!="RUNNING":
            due=job["scheduled_for"]<=stamp
            self.repo.db.execute("UPDATE generation_jobs SET profile_key=?,status=?,finished_at=COALESCE(finished_at,?),next_retry_at=NULL,error_code=NULL,error_message=NULL WHERE id=?",
                (profile.key(),"COMPLETED" if due else job["status"],stamp if due else None,job["id"]))
        generation_id="generation_"+uuid.uuid4().hex
        self.repo.db.execute("INSERT INTO manual_refresh_requests(id,user_id,reason,status,stage,requested_at,updated_at,selected_voice_id) VALUES(?,?,'PREFERENCES_CHANGED','PENDING','QUEUED',?,?,?)",
            (generation_id,user_id,stamp,stamp,prefs.get("audio_voice_id")))
        self.repo.db.commit()
        return {"scheduled":True,"generation_id":generation_id,"reason":"PREFERENCES_CHANGED"}

    def run_forever(self, interval_seconds=None):
        interval = max(1.0, float(interval_seconds or os.getenv("SCHEDULER_POLL_SECONDS", "60")))
        try:
            while True:
                self.run_once()
                time.sleep(interval)
        except KeyboardInterrupt:
            return


_ENGINE_MAIN = None


def _engine_collect_sources():
    """engine/main.py's collector, imported once (it used to be re-executed with runpy on every refresh)."""
    global _ENGINE_MAIN
    if _ENGINE_MAIN is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("newzi_engine_main", ENGINE_ROOT / "main.py")
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        _ENGINE_MAIN = module
    return _ENGINE_MAIN.collect_sources


class NewsRefreshWorker:
    """Refresh the shared article pool on a bounded cadence, independently of users."""
    def __init__(self, repo, interval_seconds=None, timeout_minutes=None):
        self.repo=repo
        self.interval_seconds=max(30,int(interval_seconds if interval_seconds is not None else os.getenv("NEWS_REFRESH_INTERVAL_SECONDS","600")))
        self.timeout_minutes=int(timeout_minutes if timeout_minutes is not None else os.getenv("INGESTION_TIMEOUT_MINUTES",30))

    @staticmethod
    def owner():
        import socket
        return f"{socket.gethostname()}:{os.getpid()}"

    @staticmethod
    def _process_alive(pid):
        if os.name == "nt":
            return True  # no safe liveness probe here (os.kill would terminate it): the timeout applies
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def recover_interrupted(self):
        """At worker start: fail a RUNNING ingestion whose process is gone (killed by a restart or deploy).

        Without this a deploy left the run RUNNING and blocked collection for INGESTION_TIMEOUT_MINUTES.
        A run of another host, or of a process still alive, is left alone; one recorded before owners
        existed belongs to a process that did not survive the deploy that added them."""
        import socket
        host = socket.gethostname(); released = 0
        for row in self.repo.db.execute("SELECT id,owner FROM content_ingestion_runs WHERE status='RUNNING'").fetchall():
            owner_host, _, pid = (row["owner"] or "").rpartition(":")
            if row["owner"] and (owner_host != host or not pid.isdigit() or self._process_alive(int(pid))):
                continue
            released += self.repo.db.execute("UPDATE content_ingestion_runs SET status='FAILED',completed_at=?,errors_json=? WHERE id=? AND status='RUNNING'",
                (now_iso(), json.dumps({"error_code": "WORKER_RESTARTED", "message": "ingestion interrupted by a worker restart"}), row["id"])).rowcount
        self.repo.db.commit()
        if released:
            import logging
            logging.getLogger(__name__).warning("released %s ingestion run(s) interrupted by a restart", released)
        return released

    def _recover_stale(self, now):
        """Fail a RUNNING ingestion whose process died; otherwise it blocks every later refresh."""
        cutoff=iso(now-timedelta(minutes=self.timeout_minutes))
        cur=self.repo.db.execute("UPDATE content_ingestion_runs SET status='FAILED',completed_at=?,errors_json=? WHERE status='RUNNING' AND started_at<?",
            (iso(now),json.dumps({"error_code":"WORKER_TIMEOUT","message":"stale RUNNING ingestion recovered"}),cutoff))
        if cur.rowcount:
            import logging
            logging.getLogger(__name__).warning("recovered %s stale ingestion run(s) older than %s min",cur.rowcount,self.timeout_minutes)
        return cur.rowcount

    def refresh_if_due(self, force=False):
        now=datetime.now(timezone.utc); stamp=iso(now); refresh_id=None
        self.repo.db.begin_immediate()
        try:
            recovered=self._recover_stale(now)
            running=self.repo.db.execute("SELECT * FROM content_ingestion_runs WHERE status='RUNNING' ORDER BY started_at DESC LIMIT 1").fetchone()
            if running:
                self.repo.db.commit()
                return {**dict(running),"skipped":"IN_PROGRESS"}
            last=self.repo.db.execute("SELECT * FROM content_ingestion_runs ORDER BY started_at DESC LIMIT 1").fetchone()
            if not force and not recovered and last and last["completed_at"]:
                completed=parse(last["completed_at"])
                if completed.tzinfo is None: completed=completed.replace(tzinfo=timezone.utc)
                backoff=self.interval_seconds if last["status"] in {"READY","PARTIAL"} else min(self.interval_seconds,120)
                if (now-completed).total_seconds()<backoff:
                    self.repo.db.commit()
                    return {**dict(last),"skipped":"NOT_DUE"}
            refresh_id="ingestion_"+uuid.uuid4().hex
            self.repo.db.execute("INSERT INTO content_ingestion_runs(id,status,started_at,owner) VALUES(?,'RUNNING',?,?)",(refresh_id,stamp,self.owner()))
            self.repo.db.commit()
        except Exception:
            self.repo.db.rollback(); raise

        total_started=time.monotonic()
        try:
            collect_sources=_engine_collect_sources()
            try: stats,changed=collect_sources(incremental=True)
            except TypeError: stats,changed=collect_sources()
            from .content import sync_content_incremental, get_content_revision
            revision_before=get_content_revision(self.repo)["revision"]
            index_started=time.monotonic(); index=sync_content_incremental(self.repo,changed,ingestion_run_id=refresh_id)
            index_ms=int((time.monotonic()-index_started)*1000); revision_after=get_content_revision(self.repo)["revision"]
            completed=now_iso(); source_errors=stats.get("source_errors",{})
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
                (now_iso(),json.dumps({"error":str(exc)[:500],"worker_total_ms":int((time.monotonic()-total_started)*1000)},ensure_ascii=False),refresh_id))
            self.repo.db.commit(); raise


class BriefingGenerationWorker:
    def __init__(self, repo, generator=None, clock=None, max_attempts=None, timeout_minutes=None, worker_id=None, audio_service=None):
        self.repo=repo; self.generator=generator or EngineBriefingGenerator(repo); self.clock=clock or Clock(); self.max_attempts=int(max_attempts if max_attempts is not None else os.getenv("GENERATION_MAX_RETRIES",2)); self.timeout_minutes=int(timeout_minutes if timeout_minutes is not None else os.getenv("WORKER_JOB_TIMEOUT_MINUTES",30)); self.worker_id=worker_id or "worker_"+uuid.uuid4().hex; self.audio_service=audio_service
    def recover_stale(self):
        cutoff=iso(datetime.now(timezone.utc)-timedelta(minutes=self.timeout_minutes)); now=now_iso()
        cur=self.repo.db.execute("""UPDATE generation_jobs SET status=CASE WHEN attempt_count<max_attempts THEN 'RETRY' ELSE 'FAILED' END,
            next_retry_at=CASE WHEN attempt_count<max_attempts THEN ? ELSE NULL END,finished_at=CASE WHEN attempt_count<max_attempts THEN NULL ELSE ? END,
            error_code='WORKER_TIMEOUT',error_message='stale RUNNING job recovered',worker_id=NULL WHERE status='RUNNING' AND started_at<?""",(now,now,cutoff)); self.repo.db.commit(); return cur.rowcount
    def claim(self):
        self.recover_stale()
        try:
            self.repo.db.begin_immediate()
            row=self.repo.db.execute("""SELECT * FROM generation_jobs j WHERE status IN ('PENDING','RETRY')
                AND (next_retry_at IS NULL OR next_retry_at<=?)
                AND NOT EXISTS (SELECT 1 FROM generation_jobs running WHERE running.profile_key=j.profile_key
                    AND running.briefing_date=j.briefing_date AND running.status='RUNNING')
                ORDER BY scheduled_for LIMIT 1""",(now_iso(),)).fetchone()
            if not row: self.repo.db.rollback(); return None
            cur=self.repo.db.execute("UPDATE generation_jobs SET status='RUNNING',started_at=?,attempt_count=attempt_count+1,worker_id=? WHERE id=? AND status IN ('PENDING','RETRY')",(now_iso(),self.worker_id,row["id"]));
            if cur.rowcount != 1: self.repo.db.rollback(); return None
            self.repo.db.commit(); return dict(self.repo.db.execute("SELECT * FROM generation_jobs WHERE id=?",(row["id"],)).fetchone())
        except Exception: self.repo.db.rollback(); raise

    def _refresh_content_index(self):
        """Run due content refreshes without coupling generation to a per-user action."""
        return NewsRefreshWorker(self.repo).refresh_if_due()

    def _claim_manual_refresh(self):
        try:
            self.repo.db.begin_immediate()
            row=self.repo.db.execute("SELECT * FROM manual_refresh_requests WHERE status='PENDING' ORDER BY requested_at LIMIT 1").fetchone()
            if not row:
                self.repo.db.rollback(); return None
            now=now_iso()
            self.repo.db.execute("UPDATE manual_refresh_requests SET status='GENERATING',stage='INGESTION',started_at=?,updated_at=? WHERE id=? AND status='PENDING'",(now,now,row['id']))
            self.repo.db.commit()
            return dict(self.repo.db.execute("SELECT * FROM manual_refresh_requests WHERE id=?",(row['id'],)).fetchone())
        except Exception:
            self.repo.db.rollback(); raise

    def _run_manual_refresh(self, request):
        request_id=request['id']; now=now_iso()
        try:
            prefs=self.repo.get_preferences(request['user_id'])
            if not prefs or (prefs.get('content_scope', 'selected') != 'all' and not prefs.get('topics')):
                raise GenerationError('PREFERENCES_INCOMPLETE','briefing preferences are unavailable')
            from .briefing_slots import slot_for
            slot_number=request.get('slot') or 1
            on_demand=request.get('reason')=='ON_DEMAND'
            profile=BriefingProfile.for_slot(prefs,slot_for(self.repo,request['user_id'],slot_number,prefs))
            if request.get('reason') in ('PREFERENCES_CHANGED','ON_DEMAND'):
                # Speed matters here: compose from the shared index the periodic refresh keeps current
                # (no ingestion is owned by this request, so failures never touch an ingestion run).
                ingestion_id=None
            else:
                ingestion=self._refresh_content_index(); ingestion_id=ingestion['id']
            self.repo.db.execute("UPDATE manual_refresh_requests SET ingestion_run_id=?,stage='COMPOSITION',updated_at=? WHERE id=?",(ingestion_id,now_iso(),request_id)); self.repo.db.commit()
            from .content import compose
            local_date=datetime.now(ZoneInfo(prefs['timezone'])).date().isoformat()
            # "Gerar agora" tells only what is new since the day's earlier briefings, never a repeat of them.
            payload=compose(self.repo,profile.topics,profile.language,profile.briefing_size,profile.country_scope,briefing_date=local_date,user_id=request['user_id'],tz=prefs['timezone'],since_today=on_demand,only_new=on_demand)
            if not payload.get('items'):
                raise GenerationError('NO_ELIGIBLE_CONTENT','fresh ingestion produced no eligible briefing items')
            edition_profile=profile.key()+'_manual_'+request_id
            edition_id,_=self._persist_edition({'briefing_date':local_date},profile,payload,edition_profile_key=edition_profile,generation_reason='MANUAL_REFRESH',ingestion_run_id=ingestion_id,generation_id=request_id,user_id=request['user_id'])
            voice=self.audio_service.effective_voice(prefs.get('audio_voice_id'),profile.language) if self.audio_service and self.repo.config.audio_enabled else None
            self.repo.db.execute("UPDATE manual_refresh_requests SET edition_id=?,selected_voice_id=?,stage=?,status=?,updated_at=? WHERE id=?",
                (edition_id,voice,'AUDIO_QUEUED' if voice else 'CONTENT_READY','GENERATING' if voice else 'FAILED',now_iso(),request_id)); self.repo.db.commit()
            if voice:
                audio_result=self.audio_service.request(edition_id,profile.language,voice)
                audio_job=self.repo.db.execute("SELECT id FROM audio_generation_jobs WHERE edition_id=? AND language=? AND voice=? ORDER BY created_at DESC LIMIT 1",(edition_id,profile.language,voice)).fetchone()
                self.repo.db.execute("UPDATE manual_refresh_requests SET audio_job_id=?,stage='AUDIO_QUEUED',updated_at=? WHERE id=?",(audio_job['id'] if audio_job else None,now_iso(),request_id)); self.repo.db.commit()
                if audio_result.get('status')=='READY': self._publish_manual_refreshes()
            return {'worker_run_id':'worker_'+uuid.uuid4().hex,'jobs_claimed':1,'jobs_completed':1,'jobs_retried':0,'jobs_failed':0,'edition_generation_count':1,'users_served_by_edition':1,'manual_generation_id':request_id,'edition_id':edition_id}
        except Exception as exc:
            if isinstance(exc,database.IntegrityError): self.repo.db.rollback()  # PostgreSQL aborts the whole transaction
            if isinstance(exc,database.IntegrityError) and self.repo.db.execute("SELECT 1 FROM content_ingestion_runs WHERE status='RUNNING' LIMIT 1").fetchone():
                self.repo.db.execute("UPDATE manual_refresh_requests SET status='PENDING',stage='WAITING_INGESTION',updated_at=? WHERE id=?",(now_iso(),request_id)); self.repo.db.commit()
                return {'worker_run_id':'worker_'+uuid.uuid4().hex,'jobs_claimed':0,'jobs_completed':0,'jobs_retried':0,'jobs_failed':0,'edition_generation_count':0,'users_served_by_edition':0,'manual_generation_id':request_id,'waiting_for_shared_ingestion':True}
            code=exc.code if isinstance(exc,GenerationError) else 'MANUAL_REFRESH_FAILED'
            if 'ingestion_id' in locals():
                self.repo.db.execute("UPDATE content_ingestion_runs SET status='FAILED',completed_at=?,errors_json=? WHERE id=? AND status='RUNNING'",(now_iso(),json.dumps({"error_code":code,"message":str(exc)[:500]}),ingestion_id))
            self.repo.db.execute("UPDATE manual_refresh_requests SET status='FAILED',stage='FAILED_FINAL',error_code=?,error_message=?,updated_at=?,finished_at=? WHERE id=?",
                (code,str(exc)[:500],now_iso(),now_iso(),request_id)); self.repo.db.commit()
            return {'worker_run_id':'worker_'+uuid.uuid4().hex,'jobs_claimed':1,'jobs_completed':0,'jobs_retried':0,'jobs_failed':1,'edition_generation_count':0,'users_served_by_edition':0,'manual_generation_id':request_id,'error_code':code}

    def _publish_manual_refreshes(self):
        if not self.audio_service: return
        rows=self.repo.db.execute("SELECT * FROM manual_refresh_requests WHERE status='GENERATING' AND edition_id IS NOT NULL AND stage IN ('AUDIO_QUEUED','AUDIO')").fetchall()
        for row in rows:
            metadata=self.audio_service.audio_for_edition(row['edition_id'],voice=row['selected_voice_id'])
            now=now_iso()
            if metadata.get('status')=='READY' and metadata.get('artifact_id'):
                prefs=self.repo.get_preferences(row['user_id']); local_now=datetime.now(ZoneInfo(prefs['timezone'])); local_date=local_now.date().isoformat()
                slot=row['slot'] or 1
                delivery=self.repo.db.execute("SELECT id FROM user_briefing_deliveries WHERE user_id=? AND local_date=? AND slot=?",(row['user_id'],local_date,slot)).fetchone()
                if slot!=1:
                    from .briefing_slots import kind_of
                    # A briefing made on request is delivered now, as a briefing of its own.
                    self.repo.db.execute("INSERT INTO user_briefing_deliveries(id,user_id,edition_id,local_date,delivery_time,timezone,status,created_at,delivered_at,selected_voice_id,active_voice_id,audio_artifact_id,audio_status,generation_stage,generation_started_at,generation_updated_at,script_id,slot,kind) VALUES(?,?,?,?,?,?,'READY',?,?,?,?,?,'READY','READY',?,?,?,?,?) ON CONFLICT(user_id,local_date,slot) DO NOTHING",
                        ('delivery_'+uuid.uuid4().hex,row['user_id'],row['edition_id'],local_date,local_now.strftime('%H:%M'),prefs['timezone'],now,now,row['selected_voice_id'],row['selected_voice_id'],metadata['artifact_id'],now,now,metadata['script_id'],slot,kind_of(slot)))
                elif delivery:
                    self.repo.db.execute("UPDATE user_briefing_deliveries SET edition_id=?,status='READY',audio_status='READY',selected_voice_id=?,active_voice_id=?,audio_artifact_id=?,script_id=?,generation_stage='READY',generation_updated_at=?,generation_error_code=NULL,generation_error_message=NULL,delivered_at=? WHERE id=?",
                        (row['edition_id'],row['selected_voice_id'],row['selected_voice_id'],metadata['artifact_id'],metadata['script_id'],now,now,delivery['id']))
                else:
                    self.repo.db.execute("INSERT INTO user_briefing_deliveries(id,user_id,edition_id,local_date,delivery_time,timezone,status,created_at,delivered_at,selected_voice_id,active_voice_id,audio_artifact_id,audio_status,generation_stage,generation_started_at,generation_updated_at,script_id) VALUES(?,?,?,?,?,?,'READY',?,?,?,?,?,'READY','READY',?,?,?) ON CONFLICT(user_id,local_date,slot) DO NOTHING",
                        ('delivery_'+uuid.uuid4().hex,row['user_id'],row['edition_id'],local_date,prefs['briefing_time'],prefs['timezone'],now,now,row['selected_voice_id'],row['selected_voice_id'],metadata['artifact_id'],now,now,metadata['script_id']))
                self.repo.db.execute("UPDATE manual_refresh_requests SET status='READY',stage='READY',audio_variant_id=?,updated_at=?,finished_at=?,error_code=NULL,error_message=NULL WHERE id=?",(metadata['artifact_id'],now,now,row['id']))
            elif metadata.get('status')=='FAILED':
                self.repo.db.execute("UPDATE manual_refresh_requests SET status='FAILED',stage='FAILED_FINAL',error_code=?,error_message=?,updated_at=?,finished_at=? WHERE id=?",(metadata.get('error_code') or 'TTS_FAILED','Audio generation failed; consult audio diagnostics.',now,now,row['id']))
        self.repo.db.commit()
    def _persist_edition(self, job, profile, payload, edition_profile_key=None, generation_reason='SCHEDULED', ingestion_run_id=None, generation_id=None, user_id=None):
        edition_profile_key=edition_profile_key or profile.key()
        existing=self.repo.db.execute("SELECT * FROM briefing_editions WHERE profile_key=? AND edition_date=?",(edition_profile_key,job["briefing_date"])).fetchone()
        if existing and existing["status"]=="READY": return existing["id"],False
        eid=existing["id"] if existing else "edition_"+uuid.uuid4().hex; t=now_iso(); items=payload.get("items",[]); status="READY" if len(items)>=MINIMUM_DELIVERABLE_ITEMS else ("PARTIAL" if items else "FAILED"); self.repo.db.execute("INSERT INTO briefing_editions(id,profile_key,edition_date,language,status,generated_at,item_count,engine_version,created_at,user_id,narration) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,generated_at=excluded.generated_at,item_count=excluded.item_count,engine_version=excluded.engine_version,created_at=excluded.created_at,user_id=excluded.user_id,narration=excluded.narration",(eid,edition_profile_key,job["briefing_date"],profile.language,status,payload.get("generated_at",t),len(items),payload.get("engine_version","phase_4.2"),t,user_id,profile.narration)); self.repo.db.execute("DELETE FROM briefing_edition_items WHERE edition_id=?",(eid,))
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
            from .briefing_slots import kind_of, slot_for
            prefs=self.repo.get_preferences(job["user_id"]); slot_number=job.get("slot") or 1
            slot=slot_for(self.repo,job["user_id"],slot_number,prefs)
            if slot is None: raise GenerationError("SLOT_REMOVED","the extra briefing no longer exists")
            profile=BriefingProfile.for_slot(prefs,slot)
            # Every user gets an edition composed at their own briefing time, never one built hours earlier for someone else.
            edition_key=user_edition_key(profile,job["user_id"],slot_number)
            existing=self.repo.db.execute("SELECT id FROM briefing_editions WHERE profile_key=? AND edition_date=? AND status='READY'",(edition_key,job["briefing_date"])).fetchone()
            if existing: eid=existing["id"]; generated=False
            else:
                compose_started=time.monotonic()
                refresh_started=time.monotonic()
                if isinstance(self.generator,EngineBriefingGenerator):
                    self._refresh_content_index()
                    self.generator.last_phase_durations['CONTENT_REFRESH']=int((time.monotonic()-refresh_started)*1000)
                payload=self.generator.generate(profile.topics,profile.language,profile.briefing_size,job["briefing_date"],profile.country_scope,user_id=job["user_id"],tz=job["timezone"],since_today=slot_number!=1)
                for phase_name,duration in getattr(self.generator,"last_phase_durations",{}).items():
                    self.repo.db.execute("INSERT INTO generation_job_phases(job_id,phase,duration_ms,recorded_at) VALUES(?,?,?,?) ON CONFLICT(job_id,phase) DO UPDATE SET duration_ms=excluded.duration_ms,recorded_at=excluded.recorded_at",(job["id"],phase_name,int(duration),now_iso()))
                self.repo.db.commit()
                if not payload.get("items"):
                    from .content import compose
                    if self.repo.db.execute("SELECT 1 FROM indexed_content LIMIT 1").fetchone():
                        fallback=compose(self.repo,profile.topics,profile.language,profile.briefing_size,profile.country_scope,briefing_date=job["briefing_date"],user_id=job["user_id"],tz=job["timezone"],since_today=slot_number!=1)
                        if fallback.get("items"): payload=fallback
                eid,generated=self._persist_edition(job,profile,payload,edition_profile_key=edition_key,user_id=job["user_id"])
                self.repo.db.execute("INSERT INTO generation_job_phases(job_id,phase,duration_ms,recorded_at) VALUES(?,?,?,?) ON CONFLICT(job_id,phase) DO UPDATE SET duration_ms=excluded.duration_ms,recorded_at=excluded.recorded_at",(job["id"],"EDITION_PERSISTENCE",int((time.monotonic()-compose_started)*1000),now_iso())); self.repo.db.commit()
            edition=self.repo.db.execute("SELECT status,item_count FROM briefing_editions WHERE id=?",(eid,)).fetchone()
            if not edition or edition["status"]!="READY" or int(edition["item_count"] or 0)<MINIMUM_DELIVERABLE_ITEMS:
                raise GenerationError("NO_DELIVERABLE_ITEMS","edition has no deliverable items")
            t=now_iso(); delivery=self.repo.db.execute("SELECT id FROM user_briefing_deliveries WHERE user_id=? AND local_date=? AND slot=?",(job["user_id"],job["briefing_date"],slot_number)).fetchone()
            delivery_id=delivery["id"] if delivery else "delivery_"+uuid.uuid4().hex
            self.repo.db.execute("""INSERT INTO user_briefing_deliveries
                (id,user_id,edition_id,local_date,delivery_time,timezone,status,created_at,delivered_at,
                 selected_voice_id,active_voice_id,audio_artifact_id,audio_status,generation_stage,
                 generation_started_at,generation_updated_at,generation_error_code,generation_error_message,script_id,slot,kind,theme)
                VALUES(?,?,?,?,?,?,?, ?,NULL,?,NULL,NULL,'PENDING','AUDIO_QUEUED',?,?,NULL,NULL,NULL,?,?,?)
                ON CONFLICT(user_id,local_date,slot) DO UPDATE SET edition_id=excluded.edition_id,status='AUDIO_QUEUED',
                selected_voice_id=excluded.selected_voice_id,audio_status='PENDING',generation_stage='AUDIO_QUEUED',
                generation_started_at=COALESCE(user_briefing_deliveries.generation_started_at,excluded.generation_started_at),
                generation_updated_at=excluded.generation_updated_at,generation_error_code=NULL,generation_error_message=NULL""",
                (delivery_id,job["user_id"],eid,job["briefing_date"],job["delivery_time"],job["timezone"],"AUDIO_QUEUED",t,prefs.get("audio_voice_id"),t,t,slot_number,kind_of(slot_number),slot.get("theme")))
            self.repo.db.execute("UPDATE generation_jobs SET status='COMPLETED',finished_at=?,error_code=NULL,error_message=NULL WHERE id=?",(t,job["id"])); self.repo.db.commit()
            scheduled=parse(job["scheduled_for"])
            queue_ms=max(0,int((datetime.now(timezone.utc)-scheduled.astimezone(timezone.utc)).total_seconds()*1000))
            self.repo.db.execute("INSERT INTO generation_job_phases(job_id,phase,duration_ms,recorded_at) VALUES(?,?,?,?) ON CONFLICT(job_id,phase) DO UPDATE SET duration_ms=excluded.duration_ms,recorded_at=excluded.recorded_at",(job["id"],"QUEUE_WAIT",queue_ms,t))
            self.repo.db.execute("INSERT INTO generation_job_phases(job_id,phase,duration_ms,recorded_at) VALUES(?,?,?,?) ON CONFLICT(job_id,phase) DO UPDATE SET duration_ms=excluded.duration_ms,recorded_at=excluded.recorded_at",(job["id"],"TOTAL_DELIVERY_CONTENT",int((time.monotonic()-total_started)*1000),t)); self.repo.db.commit()
            if self.repo.config.audio_enabled:
                try:
                    from .audio import AudioService
                    voice=self.repo.get_preferences(job["user_id"]).get("audio_voice_id")
                    audio=self.audio_service or AudioService(self.repo)
                    queued=audio.request(eid, profile.language, voice)
                    audio.attach_variant_to_delivery(delivery_id, queued)
                except Exception as exc:
                    import logging
                    self.repo.db.execute("UPDATE user_briefing_deliveries SET audio_status='FAILED',generation_stage='FAILED_FINAL',generation_error_code='AUDIO_ENQUEUE_FAILED',generation_error_message=?,generation_updated_at=? WHERE id=?",(str(exc)[:500],now_iso(),delivery_id)); self.repo.db.commit()
                    logging.getLogger(__name__).exception("audio enqueue failed for edition %s", eid)
            else:
                self.repo.db.execute("UPDATE user_briefing_deliveries SET status='CONTENT_READY',audio_status='NOT_AVAILABLE',generation_stage='CONTENT_READY',generation_updated_at=? WHERE id=?",(t,delivery_id)); self.repo.db.commit()
            from .notifications import NotificationService
            NotificationService(self.repo).enqueue_ready()
            result["jobs_completed"]=1; result["edition_generation_count"]=1 if generated else 0; result["users_served_by_edition"]=1; return result
        except GenerationError as exc: return self._failure(job,exc.code,str(exc),result)
        except Exception as exc: return self._failure(job,"ENGINE_FAILED",str(exc),result)
    def _failure(self,job,code,message,result):
        retry=job["attempt_count"] < job["max_attempts"]; status="RETRY" if retry else "FAILED"; next_at=iso(datetime.now(timezone.utc)+timedelta(minutes=2**job["attempt_count"])) if retry else None; self.repo.db.execute("UPDATE generation_jobs SET status=?,finished_at=?,next_retry_at=?,error_code=?,error_message=? WHERE id=?",(status,now_iso(),next_at,code,message,job["id"])); self.repo.db.commit(); result["jobs_retried" if retry else "jobs_failed"]+=1; return result

    def run_batch(self, batch_size=None):
        size = max(1, int(batch_size or os.getenv("WORKER_BATCH_SIZE", "20")))
        result = {"jobs_claimed": 0, "jobs_completed": 0, "jobs_retried": 0, "jobs_failed": 0,
                  "edition_generation_count": 0, "users_served_by_edition": 0}
        for _ in range(size):
            current = self.run_once()
            for key in result: result[key] += current.get(key, 0)
            if not current["jobs_claimed"]: break
            # Someone is waiting on a briefing they asked for: its audio starts in this same cycle,
            # and scheduled jobs wait for the next one.
            if current.get("manual_generation_id") and not self.manual_waiting(): break
        return result

    def manual_waiting(self):
        """A briefing asked for ("Gerar agora", new preferences) is queued and no worker has taken it yet."""
        return self.repo.db.execute("SELECT 1 FROM manual_refresh_requests WHERE status='PENDING' AND stage='QUEUED' LIMIT 1").fetchone() is not None

    def run_forever(self, interval_seconds=None, batch_size=None):
        interval = max(1.0, float(interval_seconds or os.getenv("WORKER_POLL_SECONDS", "15")))
        try:
            while True:
                self.run_batch(batch_size)
                time.sleep(interval)
        except KeyboardInterrupt:
            return


WORKER_ROLES = ("news", "schedule", "generation", "audio", "notifications", "breaking", "football", "retention")


def parse_worker_roles(value=None):
    """Roles from a list or a ``news,audio`` / ``news:audio`` string; empty or ``all`` means every role."""
    import re
    if value is None:
        value = os.getenv("WORKER_ROLES", "all")
    items = value if isinstance(value, (list, tuple, set, frozenset)) else re.split(r"[\s,:+]+", str(value))
    roles = {item.strip().lower() for item in items if item and item.strip()}
    if not roles or "all" in roles:
        return frozenset(WORKER_ROLES)
    unknown = roles - set(WORKER_ROLES)
    if unknown:
        raise ValueError("unknown worker roles: " + ", ".join(sorted(unknown)) + "; valid: " + ", ".join(WORKER_ROLES))
    return frozenset(roles)


class BriefingDeliveryWorker:
    """Runs the delivery pipeline: news refresh, scheduling, editions, audio, push and retention.

    Each stage is a role (WORKER_ROLES). One process can run every role, or several processes can
    split them, e.g. one for ``news``, one for ``audio`` and one for the rest, so a slow TTS batch
    never delays push delivery. Claims are atomic, so two processes may even share a role.
    News collection runs on its own thread so a slow source refresh never blocks the cycle, and
    every cycle records a heartbeat that /health/worker reports.
    """
    def __init__(self, repo, generator=None, interval_seconds=None, batch_size=None, roles=None):
        import socket
        from .audio import AudioService
        from .breaking import BreakingNewsService
        from .notifications import NotificationService
        self.repo=repo
        self.roles=parse_worker_roles(roles)
        self.scheduler=BriefingScheduler(repo)
        self.audio=AudioService(repo)
        self.generation=BriefingGenerationWorker(repo,generator=generator,audio_service=self.audio)
        self.news_refresh=NewsRefreshWorker(repo)
        self.notifications=NotificationService(repo)
        self.breaking=BreakingNewsService(repo)
        from .football_alerts import FootballAlertService
        self.football=FootballAlertService(repo)
        from .alerts import PersonalAlertService
        self.personal_alerts=PersonalAlertService(repo)
        self.interval_seconds=max(1.0,float(interval_seconds or os.getenv("DELIVERY_WORKER_POLL_SECONDS","15")))
        self.batch_size=max(1,int(batch_size or os.getenv("WORKER_BATCH_SIZE","20")))
        self.notification_batch=max(1,int(os.getenv("NOTIFICATION_BATCH_SIZE","200")))
        self.retention_interval=max(60.0,float(os.getenv("RETENTION_INTERVAL_SECONDS","86400")))
        self.worker_id=f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self.started_at=now_iso(); self.cycles=0
        self._refresh_thread=None; self._refresh_result=None

    def _refresh_in_background(self):
        import logging, threading
        if self._refresh_thread and self._refresh_thread.is_alive():
            return {"status":"RUNNING_IN_BACKGROUND"}
        previous=self._refresh_result

        def refresh():
            try:
                self._refresh_result=self.news_refresh.refresh_if_due()
            except Exception as exc:
                logging.getLogger(__name__).exception("periodic news refresh failed; previous indexed content remains available")
                self._refresh_result={"status":"FAILED","error":str(exc)[:200]}
            finally:
                self.repo.close_thread_connection()
        self._refresh_thread=threading.Thread(target=refresh,name="newzi-news-refresh",daemon=True)
        self._refresh_thread.start()
        return {"status":"STARTED","previous":previous}

    def _retention_if_due(self):
        from .retention import run_retention_if_due
        try:
            return run_retention_if_due(self.repo,self.retention_interval,storage=self.audio.storage)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("data retention cycle failed")
            self.repo.db.rollback(); return {"status":"FAILED","error":str(exc)[:200]}

    def run_once(self):
        roles=self.roles; result={"roles":sorted(roles)}
        if "news" in roles: result["news_refresh"]=self._refresh_in_background()
        if "schedule" in roles: result["scheduled"]=self.scheduler.run_once()
        if "generation" in roles: result["generation"]=self.generation.run_batch(self.batch_size)
        if "audio" in roles:
            result["audio_jobs_enqueued"]=self.audio.enqueue_ready_editions()
            result["audio"]=self.audio.generate_batch()
        if "generation" in roles: self.generation._publish_manual_refreshes()
        if "breaking" in roles:
            result["breaking_news"]=self.breaking.run_once()
            result["personal_alerts"]=self.personal_alerts.run_once()
        if "football" in roles: result["football_alerts"]=self.football.run_once()
        if "notifications" in roles:
            from .admin_push import dispatch_due
            result["push_campaigns"]=dispatch_due(self.repo)
            result["notifications_enqueued"]=self.notifications.enqueue_ready()
            result["notification_delivery"]=self.notifications.run_batch(self.notification_batch)
        if "retention" in roles: result["retention"]=self._retention_if_due()
        return result

    def cycle(self):
        """run_once() plus the heartbeat; an exception is logged and recorded, never raised."""
        import logging
        started=time.monotonic(); error=None; result=None
        try:
            result=self.run_once()
        except Exception as exc:
            logging.getLogger(__name__).exception("briefing delivery worker cycle failed")
            self.repo.db.rollback(); error=f"{type(exc).__name__}: {str(exc)[:300]}"
        self.cycles+=1
        try:
            self._heartbeat(error,int((time.monotonic()-started)*1000))
        except Exception:
            logging.getLogger(__name__).exception("worker heartbeat failed")
            self.repo.db.rollback()
        return result

    def _heartbeat(self, error, cycle_ms):
        stamp=now_iso()
        self.repo.db.execute("""INSERT INTO worker_heartbeats(worker_id,roles,started_at,last_cycle_at,last_success_at,last_error,cycle_ms,cycles)
            VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(worker_id) DO UPDATE SET roles=excluded.roles,last_cycle_at=excluded.last_cycle_at,
            last_success_at=COALESCE(excluded.last_success_at,worker_heartbeats.last_success_at),last_error=excluded.last_error,
            cycle_ms=excluded.cycle_ms,cycles=excluded.cycles""",
            (self.worker_id,",".join(sorted(self.roles)),self.started_at,stamp,None if error else stamp,error,cycle_ms,self.cycles))
        # Rows of processes that stopped a day ago only add noise to /health/worker.
        self.repo.db.execute("DELETE FROM worker_heartbeats WHERE last_cycle_at<?",(iso(datetime.now(timezone.utc)-timedelta(days=1)),))
        self.repo.db.commit()

    def run_forever(self):
        self.news_refresh.recover_interrupted()
        try:
            while True:
                result=self.cycle()
                # A briefing asked for while the cycle ran is taken right away, not after the pause
                # (a failed cycle still pauses, so an error never turns into a busy loop).
                if result is not None and "generation" in self.roles and self.generation.manual_waiting(): continue
                time.sleep(self.interval_seconds)
        except KeyboardInterrupt:
            return


def worker_health(repo, now=None, stale_seconds=None):
    """Liveness per worker role and queue backlog, without ids, hosts or error text."""
    now=now or datetime.now(timezone.utc)
    stale=float(stale_seconds or os.getenv("WORKER_STALE_SECONDS","300"))
    def age(value):
        return None if not value else max(0,int((now-parse(value)).total_seconds()))
    workers=[]; freshest={}
    for row in repo.db.execute("SELECT roles,last_cycle_at,last_success_at,last_error,cycle_ms FROM worker_heartbeats ORDER BY last_cycle_at DESC"):
        success_age=age(row["last_success_at"])
        workers.append({"roles":row["roles"].split(","),"last_cycle_age_seconds":age(row["last_cycle_at"]),
                        "last_success_age_seconds":success_age,"last_cycle_failed":bool(row["last_error"]),"cycle_ms":row["cycle_ms"]})
        for role in row["roles"].split(","):
            if success_age is not None and (role not in freshest or success_age<freshest[role]): freshest[role]=success_age
    missing=[role for role in WORKER_ROLES if freshest.get(role) is None or freshest[role]>stale]
    stamp=iso(now)
    def queue(sql,params=()):
        row=repo.db.execute(sql,params).fetchone()
        return {"pending":row[0],"oldest_age_seconds":age(row[1])}
    queues={
        "generation":queue("SELECT COUNT(*),MIN(scheduled_for) FROM generation_jobs WHERE status IN ('PENDING','RETRY') AND scheduled_for<=?",(stamp,)),
        "audio":queue("SELECT COUNT(*),MIN(created_at) FROM audio_generation_jobs WHERE status IN ('PENDING','GENERATING')"),
        "notifications":queue("SELECT COUNT(*),MIN(scheduled_for) FROM notification_jobs WHERE status IN ('PENDING','RUNNING') AND scheduled_for<=?",(stamp,)),
        "manual_refresh":queue("SELECT COUNT(*),MIN(requested_at) FROM manual_refresh_requests WHERE status IN ('PENDING','GENERATING')"),
    }
    ingestion=repo.db.execute("SELECT MAX(completed_at) FROM content_ingestion_runs WHERE status IN ('READY','PARTIAL')").fetchone()[0]
    return {"status":"ok" if not missing else "degraded","as_of":stamp,"stale_after_seconds":int(stale),
            "roles":{role:freshest.get(role) for role in WORKER_ROLES},"missing_roles":missing,
            "workers":workers,"queues":queues,"last_news_ingestion_age_seconds":age(ingestion)}


def serialize_edition(repo, edition_id):
    row=repo.db.execute("SELECT * FROM briefing_editions WHERE id=?",(edition_id,)).fetchone();
    if not row: return None
    image_by_article={}
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
            # Articles past the retention window keep the image stored with the edition.
            if article_id and article_id in image_by_article:
                has_indexed_sources=True
                source["image_url"]=image_by_article[article_id]
        canonical_source_image=next((source.get("image_url") for source in x["sources"] if isinstance(source,dict) and source.get("image_url")),None)
        x["image_url"]=canonical_source_image if has_indexed_sources else (x.get("image_url") or canonical_source_image)
        x.pop("primary_taxonomy_reason",None); x.pop("matched_taxonomy_ids_json",None); x.pop("user_interest_matches_json",None)
        out["items"].append(x)
    return out


def briefing_health(repo, stale_minutes=30):
    """Aggregate pipeline status without returning user identifiers or credentials."""
    now=datetime.now(timezone.utc); cutoff=iso(now-timedelta(minutes=stale_minutes))
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
    return {"as_of":iso(now),"generation_jobs":generation,"audio_jobs":audio,"deliveries":deliveries,
        "audio_queued":queued,"audio_running":running,"audio_stale":stale,"audio_failed":audio.get("FAILED",0),
        "audio_ready":audio.get("READY",0),"ready_deliveries":ready,"oldest_pending_audio_job":oldest,
        "generation_phase_avg_ms":gen_averages,"audio_phase_avg_ms":audio_averages,
        "manual_generations":manual,"latest_ingestion":({**dict(ingestion),"errors_json":json.loads(ingestion["errors_json"] or "{}"),"source_metrics":json.loads(ingestion["source_metrics_json"] or "[]")} if ingestion else None)}


def briefing_diagnostic(repo, identifier):
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

