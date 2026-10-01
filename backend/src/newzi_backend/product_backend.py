"""Product backend foundation for NEWS ENGINE Phase 4.1.

This module deliberately keeps product persistence separate from engine/cache databases.
The HTTP facade is dependency-free for local development; it can later be replaced by
FastAPI without changing the repository, adapter, or orchestration contracts.
"""
import json, logging, os, re, sqlite3, uuid
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote
from zoneinfo import ZoneInfo
from newzi_engine.topic_registry import SUPPORTED_TOPIC_IDS, TOPIC_LABELS, topic_rows, taxonomy
from .paths import BACKEND_DATA, PROJECT_ROOT
from newzi_engine.paths import ENGINE_DATA, ENGINE_ROOT

TOPICS = {code: TOPIC_LABELS[code] for code in SUPPORTED_TOPIC_IDS}
STATUSES = {"PENDING", "GENERATING", "READY", "PARTIAL", "FAILED"}
ALLOWED_ENVIRONMENTS = {"development", "staging", "production"}
log = logging.getLogger("news_engine.product")


def now_iso(): return datetime.utcnow().isoformat(timespec="seconds") + "Z"


class ProductConfig:
    def __init__(self, environ=None):
        env = environ if environ is not None else os.environ
        self.app_env = str(env.get("APP_ENV", "development")).strip().lower()
        if self.app_env not in ALLOWED_ENVIRONMENTS:
            raise ValueError("APP_ENV must be development, staging, or production")
        raw = env.get("DATABASE_URL", f"sqlite:///{(BACKEND_DATA / 'product_backend.sqlite3').as_posix()}")
        self.database_url = raw
        self.db_path = Path(raw.removeprefix("sqlite:///")) if raw.startswith("sqlite:///") else (BACKEND_DATA / "product_backend.sqlite3")
        if not self.db_path.is_absolute(): self.db_path = PROJECT_ROOT / self.db_path
        self.api_host = env.get("API_HOST", "127.0.0.1")
        self.api_port = int(env.get("API_PORT", "8090"))
        self.default_timezone = env.get("DEFAULT_TIMEZONE", "America/Sao_Paulo")
        self.default_language = env.get("DEFAULT_LANGUAGE", "pt-BR")
        self.firebase_auth_enabled = self._bool(env.get("FIREBASE_AUTH_ENABLED"), default=False)
        self.firebase_project_id = str(env.get("FIREBASE_PROJECT_ID", "")).strip()
        self.dev_endpoints_enabled = self._bool(env.get("ENABLE_DEV_ENDPOINTS"), default=self.app_env == "development")
        self.push_provider = str(env.get("PUSH_PROVIDER", "development")).strip().lower()
        self.audio_enabled = self._bool(env.get("AUDIO_ENABLED"), default=True)
        self.notifications_enabled = self._bool(env.get("NOTIFICATIONS_ENABLED"), default=True)
        self.cors_origins = tuple(x.strip() for x in env.get("CORS_ALLOW_ORIGINS", "").split(",") if x.strip())
        if self.app_env == "production" and self.dev_endpoints_enabled:
            raise ValueError("ENABLE_DEV_ENDPOINTS cannot be enabled in production")
        if self.app_env == "production" and self.push_provider == "development" and self.notifications_enabled:
            raise ValueError("production notifications require PUSH_PROVIDER=fcm or notifications disabled")

    @staticmethod
    def _bool(value, default=False):
        if value is None or value == "": return default
        normalized = str(value).strip().lower()
        if normalized not in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
            raise ValueError("boolean environment values must be true/false")
        return normalized in {"1", "true", "yes", "on"}


def validate_timezone(value):
    try: ZoneInfo(value)
    except Exception as exc: raise ValueError("timezone must be a valid IANA timezone") from exc
    return value


def validate_briefing_time(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value): raise ValueError("briefing_time must use HH:MM")
    return value


def validate_preferences(data, defaults=None):
    base = {"topics": [row["id"] for row in topic_rows() if row["enabled"]][:3], "content_scope": "selected", "language": "pt-BR", "country_scope": "BOTH", "briefing_time": "06:00", "timezone": "America/Sao_Paulo", "briefing_size": 10, "audio_enabled": False, "audio_voice_id": None}
    if defaults: base.update(defaults)
    base.update(data or {})
    if base["language"] not in {"pt-BR", "en"}: raise ValueError("unsupported language")
    canonical, unknown = taxonomy().canonicalize(base["topics"])
    if unknown: raise ValueError("topics contains unsupported topic")
    if base["content_scope"] not in {"selected", "all"}: raise ValueError("invalid content_scope")
    if not canonical and base["content_scope"] != "all": raise ValueError("at least one topic is required for selected content")
    base["topics"] = list(canonical)
    if base["country_scope"] not in {"LOCAL", "GLOBAL", "BOTH"}: raise ValueError("invalid country_scope")
    if base["briefing_size"] not in {5, 10, 15}: raise ValueError("briefing_size must be 5, 10, or 15")
    from .audio import VOICE_CATALOG
    known_voices={voice["id"] for voices in VOICE_CATALOG.values() for voice in voices}
    if base["audio_voice_id"] is not None and base["audio_voice_id"] not in known_voices: raise ValueError("unsupported audio_voice_id")
    validate_timezone(base["timezone"]); validate_briefing_time(base["briefing_time"])
    return base


class ProductRepository:
    def __init__(self, path=None, config=None):
        self.config = config or ProductConfig(); self.path = Path(path or self.config.db_path); self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=30); self.db.row_factory = sqlite3.Row; self.db.execute("PRAGMA foreign_keys=ON"); self.db.execute("PRAGMA busy_timeout=30000"); self.db.execute("PRAGMA journal_mode=WAL"); self.migrate()

    def migrate(self):
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS topics(code TEXT PRIMARY KEY, name TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, display_name TEXT NOT NULL, language TEXT NOT NULL, timezone TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS user_preferences(user_id TEXT PRIMARY KEY REFERENCES users(id), topics_json TEXT NOT NULL, language TEXT NOT NULL, country_scope TEXT NOT NULL, briefing_time TEXT NOT NULL, timezone TEXT NOT NULL, briefing_size INTEGER NOT NULL, audio_enabled INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL, content_scope TEXT NOT NULL DEFAULT 'selected');
        CREATE TABLE IF NOT EXISTS briefings(id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), briefing_date TEXT NOT NULL, language TEXT NOT NULL, timezone TEXT NOT NULL, status TEXT NOT NULL, generated_at TEXT, engine_version TEXT, item_count INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, error_message TEXT, UNIQUE(user_id, briefing_date));
        CREATE TABLE IF NOT EXISTS briefing_items(id TEXT PRIMARY KEY, briefing_id TEXT NOT NULL REFERENCES briefings(id), position INTEGER NOT NULL, event_id TEXT NOT NULL, headline TEXT NOT NULL, summary TEXT NOT NULL, why_it_matters TEXT, key_points_json TEXT NOT NULL, confidence REAL, evidence_quality TEXT, trace_id TEXT, warnings_json TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS briefing_item_sources(id INTEGER PRIMARY KEY AUTOINCREMENT, briefing_item_id TEXT NOT NULL REFERENCES briefing_items(id), publisher TEXT, url TEXT, article_id TEXT, published_at TEXT);
        CREATE TABLE IF NOT EXISTS saved_stories(user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, story_id TEXT NOT NULL, story_json TEXT NOT NULL, saved_at TEXT NOT NULL, PRIMARY KEY(user_id,story_id));
        CREATE TABLE IF NOT EXISTS saved_story_progress(user_id TEXT NOT NULL, story_id TEXT NOT NULL, progress REAL NOT NULL DEFAULT 0, updated_at TEXT NOT NULL, PRIMARY KEY(user_id,story_id), FOREIGN KEY(user_id,story_id) REFERENCES saved_stories(user_id,story_id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS article_feedback(user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, story_id TEXT NOT NULL, rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5), updated_at TEXT NOT NULL, PRIMARY KEY(user_id,story_id));
        CREATE TABLE IF NOT EXISTS saved_briefings(user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, briefing_id TEXT NOT NULL, saved_at TEXT NOT NULL, PRIMARY KEY(user_id,briefing_id));
        CREATE TABLE IF NOT EXISTS generation_runs(generation_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, briefing_date TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, duration_ms REAL, candidate_count INTEGER DEFAULT 0, accepted_count INTEGER DEFAULT 0, rejected_count INTEGER DEFAULT 0, provider_failures INTEGER DEFAULT 0, status TEXT NOT NULL, error_message TEXT);
        CREATE TABLE IF NOT EXISTS auth_sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),created_at TEXT NOT NULL,expires_at TEXT NOT NULL,revoked_at TEXT);
        """)
        preference_columns={x[1] for x in self.db.execute("PRAGMA table_info(user_preferences)")}
        if "audio_voice_id" not in preference_columns: self.db.execute("ALTER TABLE user_preferences ADD COLUMN audio_voice_id TEXT")
        if "content_scope" not in preference_columns: self.db.execute("ALTER TABLE user_preferences ADD COLUMN content_scope TEXT NOT NULL DEFAULT 'selected'")
        columns={x[1] for x in self.db.execute("PRAGMA table_info(users)")}
        if "firebase_uid" not in columns: self.db.execute("ALTER TABLE users ADD COLUMN firebase_uid TEXT")
        if "password_hash" not in columns: self.db.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        if "onboarding_status" not in columns: self.db.execute("ALTER TABLE users ADD COLUMN onboarding_status TEXT NOT NULL DEFAULT 'NOT_STARTED'")
        topic_columns={x[1] for x in self.db.execute("PRAGMA table_info(topics)")}
        for name in ("slug", "parent_id", "type"):
            if name not in topic_columns: self.db.execute(f"ALTER TABLE topics ADD COLUMN {name} TEXT")
        self.db.execute("CREATE TABLE IF NOT EXISTS taxonomy_aliases(alias TEXT PRIMARY KEY,code TEXT NOT NULL REFERENCES topics(code))")
        self.db.execute("CREATE TABLE IF NOT EXISTS taxonomy_resolution_metrics(name TEXT PRIMARY KEY,count INTEGER NOT NULL DEFAULT 0)")
        self.sync_taxonomy()
        self.db.executescript("CREATE INDEX IF NOT EXISTS idx_sessions_user_expires ON auth_sessions(user_id, expires_at); CREATE INDEX IF NOT EXISTS idx_briefings_user_date ON briefings(user_id, briefing_date);")
        self.db.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(1,?)", (now_iso(),)); self.db.commit()
        self.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_firebase_uid ON users(firebase_uid) WHERE firebase_uid IS NOT NULL"); self.db.commit()

    def sync_taxonomy(self):
        for node in taxonomy().nodes.values():
            self.db.execute("INSERT INTO topics(code,name,active,slug,parent_id,type) VALUES(?,?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET name=excluded.name,active=excluded.active,slug=excluded.slug,parent_id=excluded.parent_id,type=excluded.type", (node["id"],node["name"],int(node.get("active",True)),node.get("slug"),node.get("parent_id"),node.get("type","subject")))
            for alias in node.get("aliases", []):
                self.db.execute("INSERT OR REPLACE INTO taxonomy_aliases(alias,code) VALUES(?,?)",(alias,node["id"]))
        self.db.commit()

    def create_dev_user(self):
        uid = "dev-user-001"; t = now_iso(); self.db.execute("INSERT OR IGNORE INTO users(id,email,display_name,language,timezone,created_at,updated_at,status,onboarding_status) VALUES(?,?,?,?,?,?,?,?,?)", (uid, "dev@newzi.local", "Newzi Dev", self.config.default_language, self.config.default_timezone, t, t, "ACTIVE", "COMPLETED")); self.db.execute("""INSERT OR IGNORE INTO user_preferences
            (user_id,topics_json,language,country_scope,briefing_time,timezone,briefing_size,audio_enabled,updated_at,audio_voice_id)
            VALUES(?,?,?,?,?,?,?,?,?,?)""", (uid, json.dumps([row["id"] for row in topic_rows() if row["enabled"]][:3]), "pt-BR", "BOTH", "06:00", "America/Sao_Paulo", 10, 0, t, None)); self.db.commit(); return self.get_user(uid)

    def get_user(self, uid):
        row=self.db.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone(); return dict(row) if row else None
    def ensure_firebase_user(self, firebase_uid, email, display_name=""):
        existing = self.db.execute("SELECT * FROM users WHERE firebase_uid=? OR id=?", (firebase_uid, firebase_uid)).fetchone()
        t = now_iso()
        if existing:
            self.db.execute("UPDATE users SET firebase_uid=?,email=?,display_name=?,updated_at=? WHERE id=?", (firebase_uid, email or existing["email"], display_name or existing["display_name"], t, existing["id"]))
            self.db.commit()
            if not self.get_preferences(existing["id"]): self.save_preferences(existing["id"], {})
            return self.get_user(existing["id"])
        self.db.execute("INSERT INTO users(id,firebase_uid,email,display_name,language,timezone,created_at,updated_at,status,onboarding_status) VALUES(?,?,?,?,?,?,?,?,?,?)", (firebase_uid, firebase_uid, email or "", display_name or "", self.config.default_language, self.config.default_timezone, t, t, "ACTIVE", "NOT_STARTED"))
        self.db.commit(); self.save_preferences(firebase_uid, {})
        return self.get_user(firebase_uid)
    @staticmethod
    def public_user(user):
        if not user: return None
        return {k:user.get(k) for k in ("id","email","display_name","language","timezone","created_at","updated_at","status","onboarding_status") if k in user}
    def get_preferences(self, uid):
        row=self.db.execute("SELECT * FROM user_preferences WHERE user_id=?",(uid,)).fetchone();
        if not row: return None
        out=dict(row); out["topics"]=list(taxonomy().canonicalize(json.loads(out.pop("topics_json")))[0]); out["audio_enabled"]=bool(out["audio_enabled"]); out.setdefault("content_scope", "selected"); return out
    def save_preferences(self, uid, data):
        if "topics" in data:
            registry=taxonomy()
            alias_count=sum(bool(registry.resolve(value)) and value != registry.resolve(value) for value in data["topics"])
            unknown_count=sum(not registry.resolve(value) for value in data["topics"])
            for name, count in (("taxonomy_alias_resolutions",alias_count),("taxonomy_unknown_ids",unknown_count)):
                if count: self.db.execute("INSERT INTO taxonomy_resolution_metrics(name,count) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET count=count+excluded.count",(name,count))
            if alias_count or unknown_count: self.db.commit()
        prefs=validate_preferences(data, self.get_preferences(uid) or {}); t=now_iso(); self.db.execute("""INSERT OR REPLACE INTO user_preferences
            (user_id,topics_json,language,country_scope,briefing_time,timezone,briefing_size,audio_enabled,updated_at,audio_voice_id,content_scope)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (uid,json.dumps(prefs["topics"]),prefs["language"],prefs["country_scope"],prefs["briefing_time"],prefs["timezone"],prefs["briefing_size"],int(prefs["audio_enabled"]),t,prefs["audio_voice_id"],prefs["content_scope"])); self.db.commit(); return self.get_preferences(uid)
    def set_onboarding_status(self, uid, status):
        self.db.execute("UPDATE users SET onboarding_status=?,updated_at=? WHERE id=?",(status,now_iso(),uid)); self.db.commit()
    def list_topics(self):
        self.sync_taxonomy()
        active={row["code"] for row in self.db.execute("SELECT code FROM topics WHERE active=1")}
        counts={}
        if self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='content_taxonomy'").fetchone():
            counts={row["taxonomy_id"]:row["count"] for row in self.db.execute("SELECT taxonomy_id,COUNT(DISTINCT content_id) AS count FROM content_taxonomy GROUP BY taxonomy_id")}
        return [{**row,"content_count":counts.get(row["code"],0)} for row in topic_rows() if row["code"] in active and row["enabled"]]

    def latest_news(self, uid, limit=20, topic=None, query=None, discovery=False):
        if not self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='indexed_content'").fetchone():
            return []
        prefs=self.get_preferences(uid) or {}
        registry=taxonomy()
        selected=list(prefs.get("topics") or []) if not discovery and prefs.get("content_scope", "selected") != "all" else []
        if topic:
            resolved=registry.resolve(topic)
            if not resolved: return []
            selected=[resolved]
        selected=set(selected)
        descendants={child for parent in selected for child in registry.descendants(parent)}
        selected_with_children=sorted(selected|descendants)
        exact_ids=sorted(selected)
        clauses=["c.published_at IS NOT NULL"]
        where_params=[]
        # A real publication date older than this freshness horizon is not a
        # Home/Explore candidate; ingestion time never substitutes for it.
        freshness_cutoff=(datetime.now(timezone.utc)-timedelta(days=30)).isoformat()
        clauses.append("c.published_at>=?");where_params.append(freshness_cutoff)
        if prefs.get("country_scope")=="LOCAL": clauses.append("c.source_country='BR'")
        elif prefs.get("country_scope")=="GLOBAL": clauses.append("(c.source_country IS NULL OR c.source_country<>'BR')")
        content_columns={row[1] for row in self.db.execute("PRAGMA table_info(indexed_content)")}
        has_taxonomy=bool(self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='content_taxonomy'").fetchone())
        if selected_with_children and has_taxonomy:
            clauses.append("EXISTS (SELECT 1 FROM content_taxonomy interest WHERE interest.content_id=c.id AND interest.taxonomy_id IN ("+",".join("?" for _ in selected_with_children)+"))")
            where_params.extend(selected_with_children)
        if query:
            clauses.append("(c.title LIKE ? OR c.description LIKE ?)")
            where_params.extend([f"%{query[:100]}%",f"%{query[:100]}%"])
        image_column="c.image_url" if "image_url" in content_columns else "NULL"
        event_column="COALESCE(NULLIF(c.event_id,''),c.id)" if "event_id" in content_columns else "c.id"
        quality_column="c.quality_score" if "quality_score" in content_columns else "0"
        language_column="c.source_language" if "source_language" in content_columns else "''"
        source_id_column="c.source_id" if "source_id" in content_columns else "c.source_name"
        tag_join="LEFT JOIN content_taxonomy t ON t.content_id=c.id" if has_taxonomy else "LEFT JOIN (SELECT NULL AS content_id,NULL AS taxonomy_id,NULL AS score WHERE 0) t ON t.content_id=c.id"
        interest_params=[]
        interest_parts=[]
        if exact_ids and has_taxonomy:
            interest_parts.append("WHEN t.taxonomy_id IN ("+",".join("?" for _ in exact_ids)+") THEN 2")
            interest_params.extend(exact_ids)
        if selected_with_children and has_taxonomy:
            interest_parts.append("WHEN t.taxonomy_id IN ("+",".join("?" for _ in selected_with_children)+") THEN 1")
            interest_params.extend(selected_with_children)
        interest_case="MAX(CASE "+" ".join(interest_parts)+" ELSE 0 END)" if interest_parts else "0"
        primary_topic=("(SELECT topic.taxonomy_id FROM content_taxonomy topic WHERE topic.content_id=c.id ORDER BY topic.score DESC,topic.taxonomy_id LIMIT 1)" if has_taxonomy else "NULL")
        query_params=[*interest_params,prefs.get("language") or "pt-BR",*where_params,min(300,max(1,int(limit)*10))]
        sql=("WITH candidates AS (SELECT c.id,c.title,c.description,c.source_name,"+source_id_column+" AS source_id,c.url,c.published_at,"
             +image_column+" AS image_url,"+language_column+" AS source_language,"+quality_column+" AS quality_score,"
             +event_column+" AS event_key,"+interest_case+" AS interest_score,"
             +"CASE WHEN "+language_column+"=? THEN 1 ELSE 0 END AS language_match,"+primary_topic+" AS primary_taxonomy_id ")
        sql += "FROM indexed_content c "+tag_join+" WHERE "+" AND ".join(clauses)+" GROUP BY c.id), ranked AS (SELECT candidates.*,ROW_NUMBER() OVER(PARTITION BY event_key ORDER BY interest_score DESC,language_match DESC,published_at DESC,quality_score DESC,id) AS event_rank FROM candidates) SELECT * FROM ranked WHERE event_rank=1 ORDER BY published_at DESC,interest_score DESC,quality_score DESC,id LIMIT ?"
        rows=self.db.execute(sql,query_params).fetchall()
        source_counts={};output=[]
        remaining=list(rows)
        while remaining and len(output)<max(1,min(int(limit),30)):
            scored=[]
            for row in remaining:
                published=datetime.fromisoformat(row["published_at"].replace("Z","+00:00"))
                if published.tzinfo is None: published=published.replace(tzinfo=timezone.utc)
                age_days=max(0.0,(datetime.now(timezone.utc)-published).total_seconds()/86400)
                freshness=max(0.0,1.0-age_days/30.0)
                interest=float(row["interest_score"] or 0)/2.0
                language=float(row["language_match"] or 0)
                quality=max(0.0,min(1.0,float(row["quality_score"] or 0)/15.0))
                diversity_penalty=min(0.36,source_counts.get(row["source_id"],0)*0.12)
                score=0.46*interest+0.30*freshness+0.14*language+0.10*quality-diversity_penalty
                scored.append((score,row))
            _,best=max(scored,key=lambda pair:(pair[0],pair[1]["published_at"],pair[1]["id"]))
            remaining.remove(best);source_counts[best["source_id"]]=source_counts.get(best["source_id"],0)+1
            taxonomy_id=best["primary_taxonomy_id"]
            label=registry.nodes.get(taxonomy_id,{}).get("name") if taxonomy_id else None
            output.append({"id":best["id"],"position":len(output)+1,"headline":best["title"],"summary":best["description"] or best["title"],
                "category":label,"primary_taxonomy_id":taxonomy_id,"primary_taxonomy_label":label,"published_at":best["published_at"],
                "image_url":best["image_url"],"sources":[{"publisher":best["source_name"],"url":best["url"],"article_id":best["id"],"published_at":best["published_at"],"image_url":best["image_url"]}],"key_points":[]})
        return output

    def _canonical_article_image(self, story):
        """Hydrate saved legacy snapshots from the article's single indexed image."""
        if not isinstance(story,dict) or not story.get("id"):
            return story
        if not self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='indexed_content'").fetchone():
            return story
        columns={row[1] for row in self.db.execute("PRAGMA table_info(indexed_content)")}
        if "image_url" not in columns:
            return story
        source_rows=[source for source in story.get("sources",[]) if isinstance(source,dict)]
        article_ids=[story["id"],*(source.get("article_id") for source in source_rows if source.get("article_id"))]
        image_url=None
        for article_id in article_ids:
            row=self.db.execute("SELECT image_url FROM indexed_content WHERE id=?",(article_id,)).fetchone()
            if row and row["image_url"]:
                image_url=row["image_url"]
                break
        image_url=image_url or story.get("image_url")
        sources=[{**source,"image_url":image_url} if isinstance(source,dict) else source for source in story.get("sources",[])]
        return {**story,"image_url":image_url,"sources":sources}

    @staticmethod
    def _saved_story(story):
        allowed=("id","position","headline","summary","category","primary_taxonomy_id","primary_taxonomy_label","why_it_matters","key_points","sources","published_at","reading_time_minutes","image_url")
        clean={key:story.get(key) for key in allowed if key in story}
        if not isinstance(clean.get("id"),str) or not clean["id"] or not isinstance(clean.get("headline"),str) or not clean["headline"]:
            raise ValueError("story id and headline are required")
        clean["key_points"]=clean.get("key_points") if isinstance(clean.get("key_points"),list) else []
        clean["sources"]=clean.get("sources") if isinstance(clean.get("sources"),list) else []
        return clean

    def saved_stories(self, uid, limit=None, offset=0, topic_id=None):
        rows=self.db.execute("""SELECT s.story_json,s.saved_at,p.progress,p.updated_at AS progress_updated_at
            FROM saved_stories s LEFT JOIN saved_story_progress p ON p.user_id=s.user_id AND p.story_id=s.story_id
            WHERE s.user_id=? ORDER BY s.saved_at DESC""",(uid,)).fetchall()
        registry=taxonomy(); result=[]
        for row in rows:
            story=self._canonical_article_image(json.loads(row["story_json"]))
            raw=story.get("primary_taxonomy_id") or story.get("primary_taxonomy_label") or story.get("category")
            canonical=registry.resolve(raw) if raw else None
            if topic_id:
                if topic_id=="__OTHER__":
                    if canonical: continue
                elif canonical!=topic_id: continue
            story["saved_at"]=row["saved_at"]
            story["reading_progress"]=round(float(row["progress"] or 0),1)
            story["reading_updated_at"]=row["progress_updated_at"]
            result.append(story)
        start=max(0,int(offset or 0))
        return result[start:start+limit] if limit is not None else result[start:]

    def saved_story_progress(self, uid, story_id, progress):
        if not self.db.execute("SELECT 1 FROM saved_stories WHERE user_id=? AND story_id=?",(uid,story_id)).fetchone(): return False
        value=max(0.0,min(100.0,float(progress)))
        self.db.execute("INSERT INTO saved_story_progress(user_id,story_id,progress,updated_at) VALUES(?,?,?,?) ON CONFLICT(user_id,story_id) DO UPDATE SET progress=excluded.progress,updated_at=excluded.updated_at",(uid,story_id,value,now_iso()))
        self.db.commit(); return True

    def saved_overview(self, uid):
        registry=taxonomy()
        stories=self.db.execute("""SELECT s.story_json,s.saved_at,p.progress,p.updated_at AS progress_updated_at
            FROM saved_stories s LEFT JOIN saved_story_progress p ON p.user_id=s.user_id AND p.story_id=s.story_id
            WHERE s.user_id=? ORDER BY s.saved_at DESC""",(uid,)).fetchall()
        counts={}; topic_order={node_id:node.get("display_order",0) for node_id,node in registry.nodes.items()}
        continue_reading=None
        progress_rows=self.db.execute("""SELECT s.story_json,s.saved_at,p.progress,p.updated_at AS progress_updated_at
            FROM saved_story_progress p JOIN saved_stories s ON s.user_id=p.user_id AND s.story_id=p.story_id
            WHERE p.user_id=? AND p.progress>0 AND p.progress<100 ORDER BY p.updated_at DESC LIMIT 1""",(uid,)).fetchone()
        if progress_rows:
            continue_reading=self._canonical_article_image(json.loads(progress_rows["story_json"]))
            continue_reading.update({"saved_at":progress_rows["saved_at"],"reading_progress":round(float(progress_rows["progress"]),1),"reading_updated_at":progress_rows["progress_updated_at"]})
        recent=[{"type":"article","saved_at":row["saved_at"],"item":self._canonical_article_image(json.loads(row["story_json"])),"reading_progress":round(float(row["progress"] or 0),1)} for row in stories]
        for row in self.db.execute("SELECT briefing_id,saved_at FROM saved_briefings WHERE user_id=? ORDER BY saved_at DESC LIMIT 100",(uid,)):
            briefing=self.briefing_for_user(uid,row["briefing_id"])
            if briefing: recent.append({"type":"briefing","saved_at":row["saved_at"],"briefing":briefing})
        recent.sort(key=lambda item:item.get("saved_at") or "",reverse=True)
        for row in stories:
            story=json.loads(row["story_json"])
            raw=story.get("primary_taxonomy_id") or story.get("primary_taxonomy_label") or story.get("category")
            canonical=registry.resolve(raw) if raw else None
            key=canonical or "__OTHER__"
            counts[key]=counts.get(key,0)+1
        topics=[{"id":topic_id,"name":registry.nodes[topic_id]["name"],"count":count,"order":topic_order.get(topic_id,0)} for topic_id,count in counts.items() if topic_id!="__OTHER__"]
        topics.sort(key=lambda topic:(-topic["count"],topic["order"],topic["id"]))
        if counts.get("__OTHER__"):
            topics.append({"id":"__OTHER__","name":"Outros","count":counts["__OTHER__"],"order":10**9})
        return {"saved_count":len(stories),"continue_reading":continue_reading,"topic_summary":topics,"recent_items":recent[:12]}

    def save_story(self, uid, story):
        clean=self._canonical_article_image(self._saved_story(story)); self.db.execute("INSERT OR REPLACE INTO saved_stories(user_id,story_id,story_json,saved_at) VALUES(?,?,?,?)",(uid,clean["id"],json.dumps(clean,ensure_ascii=False),now_iso())); self.db.commit(); return clean

    def remove_saved_story(self, uid, story_id):
        cursor=self.db.execute("DELETE FROM saved_stories WHERE user_id=? AND story_id=?",(uid,story_id)); self.db.commit(); return cursor.rowcount>0

    def article_feedback(self, uid, story_id, rating=None):
        if rating is not None:
            self.db.execute("INSERT INTO article_feedback(user_id,story_id,rating,updated_at) VALUES(?,?,?,?) ON CONFLICT(user_id,story_id) DO UPDATE SET rating=excluded.rating,updated_at=excluded.updated_at",(uid,story_id,rating,now_iso())); self.db.commit()
        row=self.db.execute("SELECT rating,updated_at FROM article_feedback WHERE user_id=? AND story_id=?",(uid,story_id)).fetchone()
        return {"rating":row["rating"],"updated_at":row["updated_at"]} if row else {"rating":None,"updated_at":None}

    def briefing_for_user(self, uid, briefing_id):
        delivery=self.db.execute("SELECT * FROM user_briefing_deliveries WHERE id=? AND user_id=?",(briefing_id,uid)).fetchone()
        if delivery:
            from .scheduling import serialize_edition
            edition=serialize_edition(self,delivery["edition_id"])
            return {"id":delivery["id"],"date":delivery["local_date"],"status":delivery["status"],"generated_at":(edition or {}).get("generated_at"),"items":(edition or {}).get("items",[])}
        row=self.db.execute("SELECT * FROM briefings WHERE id=? AND user_id=?",(briefing_id,uid)).fetchone()
        return self.serialize_briefing(row) if row else None

    def save_briefing(self, uid, briefing_id):
        if not self.briefing_for_user(uid,briefing_id): return False
        self.db.execute("INSERT OR REPLACE INTO saved_briefings(user_id,briefing_id,saved_at) VALUES(?,?,?)",(uid,briefing_id,now_iso())); self.db.commit(); return True

    def saved_briefings(self, uid):
        result=[]
        for row in self.db.execute("SELECT briefing_id,saved_at FROM saved_briefings WHERE user_id=? ORDER BY saved_at DESC LIMIT 100",(uid,)):
            briefing=self.briefing_for_user(uid,row["briefing_id"])
            if briefing: briefing["saved_at"]=row["saved_at"]; result.append(briefing)
        return result

    def remove_saved_briefing(self, uid, briefing_id):
        cursor=self.db.execute("DELETE FROM saved_briefings WHERE user_id=? AND briefing_id=?",(uid,briefing_id)); self.db.commit(); return cursor.rowcount>0

    def briefing_row(self, uid, local_date): return self.db.execute("SELECT * FROM briefings WHERE user_id=? AND briefing_date=?",(uid,local_date)).fetchone()
    def serialize_briefing(self, row):
        if not row: return None
        out=dict(row); items=[]
        for item in self.db.execute("SELECT * FROM briefing_items WHERE briefing_id=? ORDER BY position",(row["id"],)):
            x=dict(item); x["key_points"]=json.loads(x.pop("key_points_json")); x["warnings"]=json.loads(x.pop("warnings_json")); x["sources"]= [dict(s) for s in self.db.execute("SELECT publisher,url,article_id,published_at FROM briefing_item_sources WHERE briefing_item_id=?",(x["id"],))]
            has_indexed_sources=False
            for source in x["sources"]:
                article_id=source.get("article_id")
                if article_id:
                    has_indexed_sources=True
                    source["image_url"]=self._canonical_article_image({"id":article_id}).get("image_url")
            canonical_source_image=next((source.get("image_url") for source in x["sources"] if source.get("image_url")),None)
            x["image_url"]=canonical_source_image if has_indexed_sources else (x.get("image_url") or canonical_source_image)
            x.pop("briefing_id",None); x.pop("created_at",None); items.append(x)
        out["date"]=out.pop("briefing_date"); out.pop("error_message",None); out["items"]=items; out.pop("created_at",None); return out

    def list_briefings(self, uid): return [self.serialize_briefing(x) for x in self.db.execute("SELECT * FROM briefings WHERE user_id=? ORDER BY briefing_date DESC",(uid,))]

    def persist_briefing(self, uid, local_date, payload, prefs, generation_id):
        existing=self.briefing_row(uid,local_date)
        if existing and existing["status"] in {"READY", "GENERATING"}: return self.serialize_briefing(existing), "already_exists"
        bid=existing["id"] if existing else "briefing_"+uuid.uuid4().hex; status=payload.get("status", "READY"); items=payload.get("items",[]); t=now_iso()
        self.db.execute("INSERT OR REPLACE INTO briefings VALUES(?,?,?,?,?,?,?,?,?,?,?)",(bid,uid,local_date,prefs["language"],prefs["timezone"],status,payload.get("generated_at",t),"phase_3.3",len(items),t,payload.get("error_message")))
        self.db.execute("DELETE FROM briefing_items WHERE briefing_id=?",(bid,))
        for pos,item in enumerate(items,1):
            iid="item_"+uuid.uuid4().hex; self.db.execute("INSERT INTO briefing_items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(iid,bid,pos,item.get("event_id",""),item.get("headline",""),item.get("summary",""),item.get("why_it_matters"),json.dumps(item.get("key_points",[]),ensure_ascii=False),item.get("confidence"),item.get("evidence_quality"),item.get("provenance",{}).get("trace_id"),json.dumps(item.get("warnings",[]),ensure_ascii=False),t))
            for source in item.get("sources",[]): self.db.execute("INSERT INTO briefing_item_sources(briefing_item_id,publisher,url,article_id,published_at) VALUES(?,?,?,?,?)",(iid,source.get("publisher"),source.get("url"),source.get("article_id"),source.get("published_at")))
        self.db.commit(); return self.serialize_briefing(self.briefing_row(uid,local_date)), "created"


class Phase33Adapter:
    def __init__(self, path=None): self.path=Path(path or (ENGINE_ROOT / "fixtures" / "briefing.json"))
    def load(self):
        data=json.loads(self.path.read_text(encoding="utf-8")); items=[]
        for raw in data.get("items",[]):
            articles=raw.get("articles",[])
            sources=raw.get("sources",[])
            if articles:
                sources=[{"publisher":a.get("source") or a.get("source_name"), "url":a.get("url"), "published_at":a.get("published_at")} for a in articles]
            headline=raw.get("headline") or raw.get("title") or ""
            summary=raw.get("summary") or (articles[0].get("title") if articles else headline)
            items.append({**raw, "headline":headline, "summary":summary, "key_points":raw.get("key_points",[headline]), "sources":sources})
        return {"status":"READY" if items else "PARTIAL", "generated_at":data.get("generated_at"), "items":items}


class BriefingOrchestrator:
    def __init__(self, repo, adapter=None, clock=None): self.repo=repo; self.adapter=adapter or Phase33Adapter(); self.clock=clock
    def _local_date(self, prefs):
        now = self.clock.now(prefs["timezone"]) if self.clock else datetime.now(ZoneInfo(prefs["timezone"]))
        return now.date().isoformat()
    def generate(self, uid, force=False):
        if not self.repo.get_user(uid): raise ValueError("user not found")
        prefs=self.repo.get_preferences(uid); local_date=self._local_date(prefs); existing=self.repo.briefing_row(uid,local_date)
        if existing and existing["status"] in {"READY", "GENERATING"} and not force: return self.repo.serialize_briefing(existing), "already_exists"
        generation_id="generation_"+uuid.uuid4().hex; started=datetime.utcnow(); self.repo.db.execute("INSERT INTO generation_runs(generation_id,user_id,briefing_date,started_at,status) VALUES(?,?,?,?,?)",(generation_id,uid,local_date,started.isoformat()+"Z","GENERATING")); self.repo.db.commit()
        try:
            payload=self.adapter.load(); result,mode=self.repo.persist_briefing(uid,local_date,payload,prefs,generation_id); finished=datetime.utcnow(); self.repo.db.execute("UPDATE generation_runs SET finished_at=?,duration_ms=?,candidate_count=?,accepted_count=?,rejected_count=?,status=? WHERE generation_id=?",(finished.isoformat()+"Z",(finished-started).total_seconds()*1000,len(payload.get("items",[])),len(payload.get("items",[])),0,"READY",generation_id)); self.repo.db.commit(); return result,mode
        except Exception as exc:
            finished=datetime.utcnow(); self.repo.db.execute("UPDATE generation_runs SET finished_at=?,duration_ms=?,status=?,error_message=? WHERE generation_id=?",(finished.isoformat()+"Z",(finished-started).total_seconds()*1000,"FAILED",str(exc),generation_id)); self.repo.db.commit(); payload={"status":"FAILED","items":[],"error_message":"generation failed"}; return self.repo.persist_briefing(uid,local_date,payload,prefs,generation_id)[0], "failed"


class ProductAPI:
    def __init__(self, repo=None, orchestrator=None):
        self.repo=repo or ProductRepository(); self.orchestrator=orchestrator or BriefingOrchestrator(self.repo)
        self.config = self.repo.config
        log.info("[Backend Auth] firebase_auth_enabled=%s project_id=%s", self.config.firebase_auth_enabled, self.config.firebase_project_id or "unset")
        from .scheduling import BriefingScheduler, BriefingGenerationWorker, ensure_phase42_schema
        from .identity import LocalIdentityProvider, LocalAuthRateLimiter
        ensure_phase42_schema(self.repo); self.scheduler=BriefingScheduler(self.repo)
        from .scheduling import FixtureBriefingGenerator
        generator=FixtureBriefingGenerator() if os.getenv("BRIEFING_GENERATOR","engine")=="fixture" else None
        self.worker=BriefingGenerationWorker(self.repo,generator=generator)
        if self.config.firebase_auth_enabled:
            from .firebase_identity import FirebaseAdminIdentityProvider
            self.identity = FirebaseAdminIdentityProvider(self.repo, self.config.firebase_project_id)
        else:
            self.identity=LocalIdentityProvider(self.repo)
        self.rate_limiter=LocalAuthRateLimiter()
        from .audio import AudioService, ensure_audio_schema
        ensure_audio_schema(self.repo); self.audio = AudioService(self.repo)
        from .notifications import NotificationService, ensure_notification_schema
        ensure_notification_schema(self.repo); self.notifications = NotificationService(self.repo)
    def _error(self, code, message, request_id, status): return status,{"error":{"code":code,"message":message,"request_id":request_id}}
    def _identity(self, headers):
        auth=""
        for name, value in (headers or {}).items():
            if str(name).casefold() == "authorization":
                auth=value
                break
        log.info("[Backend Auth] authorization_header_present=%s", bool(auth))
        if not auth:
            self._last_auth_failure = "AUTH_MISSING_HEADER"
            return None
        if not auth.lower().startswith("bearer "):
            self._last_auth_failure = "AUTH_INVALID_SCHEME"
            return None
        token=auth[7:].strip()
        if not token:
            self._last_auth_failure = "AUTH_EMPTY_TOKEN"
            return None
        identity=self.identity.resolve(token)
        self._last_auth_failure = getattr(self.identity, "last_verify_reason", None) if not identity else None
        return identity
    def _client_briefing(self, uid, local_date):
        delivery=self.repo.db.execute("SELECT * FROM user_briefing_deliveries WHERE user_id=? AND local_date=? ORDER BY created_at DESC LIMIT 1",(uid,local_date)).fetchone()
        if delivery:
            from .scheduling import serialize_edition
            edition=serialize_edition(self.repo,delivery["edition_id"]); items=[]
            for item in (edition or {}).get("items",[]): items.append({k:item.get(k) for k in ("id","position","headline","summary","why_it_matters","key_points","confidence","evidence_quality","sources","warnings","summary_provider","primary_taxonomy_id","primary_taxonomy_label")})
            from .scheduling import BriefingProfile
            current_key=BriefingProfile.from_preferences(self.repo.get_preferences(uid)).key()
            status=delivery["status"]; audio_status=delivery["audio_status"]; audio_metadata=None
            if status=="READY":
                if not delivery["audio_artifact_id"]: status="CONTENT_READY"; audio_status="PENDING"
                else:
                    audio_metadata=self.audio.audio_for_artifact(delivery["audio_artifact_id"])
                    if audio_metadata.get("status")!="READY": status="FAILED"; audio_status="FAILED"
            audio_url=None
            if audio_metadata and audio_metadata.get("status")=="READY":
                audio_url=("/api/v1/me/briefings/"+delivery["id"]+"/audio/file?v="+audio_metadata["asset_version"]+"&voice="+audio_metadata["voice"])
            return {"id":delivery["id"],"delivery_id":delivery["id"],"edition_id":delivery["edition_id"],"date":local_date,"status":status,"content_status":(edition or {}).get("status"),"audio_status":audio_status,"selected_voice_id":delivery["selected_voice_id"],"active_voice_id":delivery["active_voice_id"],"voice_fallback_reason":delivery["voice_fallback_reason"],"audio_variant_id":delivery["audio_artifact_id"],"active_audio_variant_id":delivery["audio_artifact_id"],"audio_url":audio_url,"audio_duration_ms":audio_metadata.get("duration_ms") if audio_url else None,"script_id":delivery["script_id"],"generation_stage":delivery["generation_stage"],"generation_started_at":delivery["generation_started_at"],"generation_updated_at":delivery["generation_updated_at"],"generation_error_code":delivery["generation_error_code"],"generated_at":(edition or {}).get("generated_at"),"items":items,"profile_stale":bool(edition and edition["profile_key"]!=current_key),"fallback_levels":sorted({w for item in items for w in item.get("warnings",[]) if isinstance(w,str) and w.startswith("FALLBACK_")})}
        row=self.repo.briefing_row(uid,local_date); legacy=self.repo.serialize_briefing(row) if row else None
        if legacy: return legacy
        job=self.repo.db.execute("SELECT status,error_code FROM generation_jobs WHERE user_id=? AND briefing_date=?",(uid,local_date)).fetchone()
        return {"date":local_date,"status":"FAILED" if job and job["status"]=="FAILED" else "PENDING","generated_at":None,"items":[],"error_code":job["error_code"] if job and job["status"]=="FAILED" else None}
    def _client_history(self, uid, limit=20, offset=0, include_audio=False):
        from .scheduling import serialize_edition
        prefs=self.repo.get_preferences(uid) if include_audio else None
        deliveries=list(self.repo.db.execute("SELECT * FROM user_briefing_deliveries WHERE user_id=? ORDER BY local_date DESC LIMIT ? OFFSET ?",(uid,limit+1,offset)))
        result=[]
        for delivery in deliveries:
            edition=serialize_edition(self.repo,delivery["edition_id"])
            row={"id":delivery["id"],"delivery_id":delivery["id"],"edition_id":delivery["edition_id"],"date":delivery["local_date"],"status":delivery["status"],"audio_status":delivery["audio_status"],"selected_voice_id":delivery["selected_voice_id"],"active_voice_id":delivery["active_voice_id"],"audio_variant_id":delivery["audio_artifact_id"],"script_id":delivery["script_id"],"generation_stage":delivery["generation_stage"],"generation_started_at":delivery["generation_started_at"],"generation_updated_at":delivery["generation_updated_at"],"generation_error_code":delivery["generation_error_code"],"generated_at":(edition or {}).get("generated_at"),"items":[{k:item.get(k) for k in ("id","position","headline","summary","why_it_matters","key_points","confidence","evidence_quality","sources","primary_taxonomy_id","primary_taxonomy_label","image_url")} for item in (edition or {}).get("items",[])]}
            progress=self.repo.db.execute("SELECT progress_seconds,duration_seconds,completed_at FROM briefing_listening_progress WHERE delivery_id=? AND user_id=?",(delivery["id"],uid)).fetchone()
            if progress:
                row.update(listening_progress_seconds=progress["progress_seconds"],listening_duration_seconds=progress["duration_seconds"],completed_at=progress["completed_at"])
            if delivery["status"]=="READY" and delivery["audio_artifact_id"]:
                metadata=self.audio.audio_for_artifact(delivery["audio_artifact_id"])
                if metadata.get("status")!="READY": row.update(status="FAILED",audio_status="FAILED",generation_error_code=metadata.get("error_code"))
                else: row["audio_duration_ms"]=metadata.get("duration_ms")
            elif delivery["status"]=="READY":
                row.update(status="CONTENT_READY",audio_status="PENDING")
            if include_audio and edition and self.config.audio_enabled:
                language=edition.get("language") or prefs.get("language")
                metadata=self.audio.audio_for_artifact(delivery["audio_artifact_id"]) if delivery["audio_artifact_id"] else {"status":"NOT_AVAILABLE"}
                row["audio_duration_ms"]=metadata.get("duration_ms") if metadata.get("status")=="READY" else None
            result.append(row)
        if result: return result[:limit], (str(offset+limit) if len(result)>limit else None)
        legacy=self.repo.list_briefings(uid); page=legacy[offset:offset+limit]; return page,(str(offset+limit) if offset+limit<len(legacy) else None)
    def _client_home(self, uid):
        preferences=self.repo.get_preferences(uid) or {}
        today=self._client_briefing(uid,self.orchestrator._local_date(preferences))
        history,_=self._client_history(uid,50)
        latest=next((item for item in history if item.get("status")=="READY" and item.get("items")),None)
        # A scheduled delivery's visual edition is the current briefing as soon
        # as it exists. Never pair an older READY audio with newer visual items.
        if today.get("items"):
            latest=today
        return {"preferences":preferences,"today_briefing":today,"latest_briefing":latest,
            "topics":self.repo.list_topics(),"latest_news":self.repo.latest_news(uid,12),
            "saved_story_ids":[row["story_id"] for row in self.repo.db.execute("SELECT story_id FROM saved_stories WHERE user_id=?",(uid,))]}

    def _preferences_updated(self, uid, previous, current, onboarding=False):
        from .scheduling import BriefingProfile
        previous=previous or {}
        old_profile=BriefingProfile.from_preferences(previous).key() if previous.get("topics") else None
        new_profile=BriefingProfile.from_preferences(current).key() if current.get("topics") else None
        if onboarding or old_profile!=new_profile:
            return self.scheduler.schedule_user_now(uid)
        if previous.get("briefing_time")!=current.get("briefing_time") or previous.get("timezone")!=current.get("timezone"):
            self.repo.db.execute("UPDATE generation_jobs SET delivery_time=?,timezone=? WHERE user_id=? AND status IN ('PENDING','RETRY')",(current["briefing_time"],current["timezone"],uid)); self.repo.db.commit()
        if previous.get("audio_voice_id")!=current.get("audio_voice_id"):
            local_date=self.orchestrator._local_date(current)
            delivery=self.repo.db.execute("SELECT id,edition_id,status FROM user_briefing_deliveries WHERE user_id=? ORDER BY local_date DESC LIMIT 1",(uid,)).fetchone()
            if delivery:
                language=self.repo.db.execute("SELECT language FROM briefing_editions WHERE id=?",(delivery["edition_id"],)).fetchone()["language"]
                result=self.audio.queue_voice_for_delivery(delivery["id"],current.get("audio_voice_id"),language)
                return {"scheduled":result.get("status") in ("PENDING","GENERATING"),"audio_status":result.get("status"),"delivery_id":delivery["id"]}
            return self.scheduler.schedule_user_now(uid)
        return {"scheduled":False,"reason":"NO_PIPELINE_CHANGE"}

    def _pipeline_diagnostic(self, uid):
        delivery=self.repo.db.execute("SELECT * FROM user_briefing_deliveries WHERE user_id=? ORDER BY local_date DESC LIMIT 1",(uid,)).fetchone()
        if not delivery: return {"delivery":None}
        job=self.repo.db.execute("SELECT id,status,attempt_count,max_attempts,scheduled_for,started_at,finished_at,error_code,error_message,profile_key FROM generation_jobs WHERE user_id=? AND briefing_date=?",(uid,delivery["local_date"])).fetchone()
        audio_job=self.repo.db.execute("SELECT id,status,stage,voice,script_version,attempt_count,max_attempts,created_at,started_at,updated_at,finished_at,error_code,error_message FROM audio_generation_jobs WHERE edition_id=? AND voice=? ORDER BY created_at DESC LIMIT 1",(delivery["edition_id"],delivery["selected_voice_id"] or delivery["active_voice_id"] or "")).fetchone()
        artifact=self.repo.db.execute("SELECT id,status,provider,voice,language,mime_type,storage_path,duration_ms,size_bytes,checksum,created_at FROM audio_artifacts WHERE id=?",(delivery["audio_artifact_id"],)).fetchone() if delivery["audio_artifact_id"] else None
        phases=list(self.repo.db.execute("SELECT phase,duration_ms,recorded_at FROM generation_job_phases WHERE job_id=? ORDER BY id",(job["id"],))) if job else []
        audio_phases=list(self.repo.db.execute("SELECT phase,duration_ms,started_at,finished_at,status,error_code FROM audio_job_phases WHERE audio_job_id=? ORDER BY id",(audio_job["id"],))) if audio_job else []
        return {"delivery":{"id":delivery["id"],"edition_id":delivery["edition_id"],"date":delivery["local_date"],"status":delivery["status"],"audio_status":delivery["audio_status"],"stage":delivery["generation_stage"],"selected_voice_id":delivery["selected_voice_id"],"active_voice_id":delivery["active_voice_id"],"script_id":delivery["script_id"],"audio_artifact_id":delivery["audio_artifact_id"],"started_at":delivery["generation_started_at"],"updated_at":delivery["generation_updated_at"],"error_code":delivery["generation_error_code"],"error_message":delivery["generation_error_message"]},"generation_job":dict(job) if job else None,"audio_job":dict(audio_job) if audio_job else None,"audio_artifact":dict(artifact) if artifact else None,"generation_phases":[dict(x) for x in phases],"audio_phases":[dict(x) for x in audio_phases]}
    def _edition_for_briefing(self, uid, briefing_id):
        delivery=self.repo.db.execute("SELECT edition_id FROM user_briefing_deliveries WHERE id=? AND user_id=?",(briefing_id,uid)).fetchone()
        if delivery: return delivery["edition_id"]
        row=self.repo.db.execute("SELECT id FROM briefings WHERE id=? AND user_id=?",(briefing_id,uid)).fetchone()
        if row: return None
        return None
    def handle(self, method, path, body=None, headers=None):
        request_id="req_"+uuid.uuid4().hex; headers=headers or {}; data=body or {}; clean=path.split("?")[0]; parts=[p for p in clean.split("/") if p]
        try:
            if method=="GET" and clean=="/health": return 200,{"status":"ok","service":"newzi-product-backend","database":"sqlite"}
            if method=="GET" and clean=="/ready":
                self.repo.db.execute("SELECT 1").fetchone()
                return 200,{"status":"ready","database":"ok"}
            if method=="GET" and parts==["api","v1","topics"]: return 200,{"items":self.repo.list_topics()}
            if method=="GET" and parts==["api","v1","client","config"]: return 200,{"supported_languages":["pt-BR","en"],"supported_briefing_sizes":[5,10,15],"country_scopes":["LOCAL","GLOBAL","BOTH"],"topics":self.repo.list_topics()}
            if parts==["api","v1","auth","register"] and method=="POST":
                if self.config.firebase_auth_enabled: return self._error("AUTH_PROVIDER_CLIENT_SIDE","use Firebase Authentication",request_id,410)
                if not self.rate_limiter.allow("register"):
                    return self._error("RATE_LIMITED","too many requests",request_id,429)
                from .identity import Identity
                try: identity,token,expires=self.identity.register(data.get("email"),data.get("password"),data.get("display_name"))
                except ValueError as exc: return self._error("VALIDATION_ERROR",str(exc),request_id,400)
                return 201,{"user":self.repo.public_user(self.repo.get_user(identity.user_id)),"session":{"token":token,"expires_at":expires}}
            if parts==["api","v1","auth","login"] and method=="POST":
                if self.config.firebase_auth_enabled: return self._error("AUTH_PROVIDER_CLIENT_SIDE","use Firebase Authentication",request_id,410)
                if not self.rate_limiter.allow("login"):
                    return self._error("RATE_LIMITED","too many requests",request_id,429)
                try: identity,token,expires=self.identity.authenticate(data)
                except PermissionError: return self._error("INVALID_CREDENTIALS","invalid credentials",request_id,401)
                return 200,{"user":self.repo.public_user(self.repo.get_user(identity.user_id)),"session":{"token":token,"expires_at":expires}}
            identity=self._identity(headers)
            if len(parts)==5 and parts[:3]==["api","v1","articles"] and parts[4]=="image" and method=="GET":
                if not identity: return self._error("AUTH_REQUIRED","authentication required",request_id,401)
                row=self.repo.db.execute("SELECT image_url FROM indexed_content WHERE id=?",(parts[3],)).fetchone()
                if not row or not row["image_url"]: return self._error("RESOURCE_NOT_FOUND","article image not found",request_id,404)
                try:
                    from .article_images import load_article_image
                    return 200,{"_image_bytes":load_article_image(row["image_url"]),"mime_type":"image/jpeg"}
                except Exception as exc:
                    from .article_images import ArticleImageError
                    if isinstance(exc,ArticleImageError):
                        log.info("[IMAGE] article_id=%s result=unavailable reason=%s",parts[3],str(exc))
                        return self._error("ARTICLE_IMAGE_UNAVAILABLE","article image unavailable",request_id,502)
                    raise
            if parts==["api","v1","auth","logout"] and method=="POST":
                if not identity: return self._error("AUTH_REQUIRED","authentication required",request_id,401)
                self.identity.revoke((headers.get("Authorization") or "")[7:].strip()); self.repo.db.execute("UPDATE push_devices SET enabled=0,invalidated_at=?,updated_at=? WHERE user_id=?",(datetime.utcnow().isoformat()+"Z",datetime.utcnow().isoformat()+"Z",identity.user_id)); self.repo.db.commit(); return 200,{"status":"ok"}
            if parts[:3]==["api","v1","me"]:
                if not identity:
                    log.warning("[Backend Auth] authorization_rejected reason=%s", getattr(self, "_last_auth_failure", None) or "AUTH_REQUIRED")
                    return self._error("AUTH_REQUIRED","authentication required",request_id,401)
                uid=identity.user_id; user=self.repo.get_user(uid)
                if parts==["api","v1","me"] and method=="GET": return 200,self.repo.public_user(user)
                if parts==["api","v1","me","preferences"]:
                    if method=="GET": return 200,self.repo.get_preferences(uid)
                    if method=="PUT":
                        previous=self.repo.get_preferences(uid); saved=self.repo.save_preferences(uid,data)
                        self._preferences_updated(uid,previous,saved)
                        return 200,saved
                if parts==["api","v1","me","audio","voices"] and method=="GET":
                    return 200,self.audio.voice_catalog(self.repo.get_preferences(uid)["language"])
                if (len(parts)==7 and parts[:5]==["api","v1","me","audio","voices"]
                        and parts[6]=="preview" and method=="GET"):
                    language=self.repo.get_preferences(uid)["language"]
                    if parts[5] not in {voice["id"] for voice in self.audio.available_voices(language)}:
                        return self._error("RESOURCE_NOT_FOUND","voice not available",request_id,404)
                    try:
                        preview=self.audio.voice_preview(parts[5],language)
                    except Exception:
                        return self._error("VOICE_PREVIEW_UNAVAILABLE","voice preview unavailable",request_id,503)
                    return 200,{"_audio_path":str(preview),"mime_type":"audio/mpeg" if preview.suffix==".mp3" else "audio/wav"}
                if parts==["api","v1","me","devices"] and method=="POST":
                    if not self.rate_limiter.allow("device:"+uid): return self._error("RATE_LIMITED","too many requests",request_id,429)
                    return 201,self.notifications.register_device(uid,data)
                if len(parts)==5 and parts[:4]==["api","v1","me","devices"] and method=="DELETE":
                    if self.notifications.disable_device(uid,parts[4]): return 204,{"status":"ok"}
                    return self._error("RESOURCE_NOT_FOUND","device not found",request_id,404)
                if parts==["api","v1","me","notification-settings"]:
                    if not self.rate_limiter.allow("notification-settings:"+uid): return self._error("RATE_LIMITED","too many requests",request_id,429)
                    if method=="GET": return 200,self.notifications.settings(uid)
                    if method=="PUT": return 200,self.notifications.save_settings(uid,data)
                if parts==["api","v1","me","content","revision"] and method=="GET":
                    from .content import get_content_revision
                    return 200,get_content_revision(self.repo)
                if parts==["api","v1","me","news"] and method=="GET":
                    params=parse_qs(path.split("?",1)[1] if "?" in path else "")
                    query=(params.get("q") or [""])[0].strip()
                    topic=(params.get("topic") or [None])[0]
                    limit=(params.get("limit") or [20])[0]
                    discovery=(params.get("discovery") or [""])[0].lower() in {"1","true","yes"}
                    return 200,{"items":self.repo.latest_news(uid,limit,topic,query,discovery)}
                if len(parts)==6 and parts[:4]==["api","v1","me","articles"] and parts[5]=="feedback":
                    story_id=unquote(parts[4])
                    if method=="GET": return 200,self.repo.article_feedback(uid,story_id)
                    if method=="PUT":
                        rating=data.get("rating")
                        if isinstance(rating,bool) or not isinstance(rating,int) or rating<1 or rating>5: return self._error("VALIDATION_ERROR","rating must be an integer between 1 and 5",request_id,400)
                        return 200,self.repo.article_feedback(uid,story_id,rating)
                if parts==["api","v1","me","home"] and method=="GET": return 200,self._client_home(uid)
                if parts==["api","v1","me","saved","overview"] and method=="GET": return 200,self.repo.saved_overview(uid)
                if len(parts)==6 and parts[:4]==["api","v1","me","saved"] and parts[5]=="progress" and method=="PUT":
                    try: progress=float(data.get("progress"))
                    except (TypeError,ValueError): return self._error("VALIDATION_ERROR","progress must be a number",request_id,400)
                    if progress<0 or progress>100: return self._error("VALIDATION_ERROR","progress must be between 0 and 100",request_id,400)
                    if self.repo.saved_story_progress(uid,unquote(parts[4]),progress): return 200,{"status":"saved","progress":progress}
                    return self._error("RESOURCE_NOT_FOUND","saved story not found",request_id,404)
                if parts==["api","v1","me","saved"]:
                    if method=="GET":
                        params=parse_qs(path.split("?",1)[1] if "?" in path else "")
                        if any(key in params for key in ("limit","cursor","topic")):
                            limit=max(1,min(int((params.get("limit") or [40])[0]),100)); offset=max(0,int((params.get("cursor") or [0])[0])); topic=(params.get("topic") or [None])[0]
                            all_items=self.repo.saved_stories(uid,topic_id=topic)
                            page=all_items[offset:offset+limit]
                            return 200,{"items":page,"next_cursor":str(offset+limit) if offset+limit<len(all_items) else None}
                        return 200,{"items":self.repo.saved_stories(uid)}
                    if method=="PUT":
                        try: return 200,{"item":self.repo.save_story(uid,data.get("story",data))}
                        except (TypeError,ValueError) as exc: return self._error("VALIDATION_ERROR",str(exc),request_id,400)
                if parts==["api","v1","me","saved-briefings"]:
                    if method=="GET": return 200,{"items":self.repo.saved_briefings(uid)}
                    if method=="PUT":
                        briefing_id=data.get("briefing_id")
                        if not isinstance(briefing_id,str) or not briefing_id: return self._error("VALIDATION_ERROR","briefing_id is required",request_id,400)
                        if not self.repo.save_briefing(uid,briefing_id): return self._error("RESOURCE_NOT_FOUND","briefing not found",request_id,404)
                        return 200,{"status":"saved"}
                if len(parts)==5 and parts[:4]==["api","v1","me","saved-briefings"] and method=="DELETE":
                    if self.repo.remove_saved_briefing(uid,unquote(parts[4])): return 200,{"status":"ok"}
                    return self._error("RESOURCE_NOT_FOUND","saved briefing not found",request_id,404)
                if len(parts)==5 and parts[:4]==["api","v1","me","saved"] and method=="DELETE":
                    if self.repo.remove_saved_story(uid,unquote(parts[4])): return 200,{"status":"ok"}
                    return self._error("RESOURCE_NOT_FOUND","saved story not found",request_id,404)
                if parts==["api","v1","me","onboarding"]:
                    if method=="GET": return 200,{"status":user.get("onboarding_status","NOT_STARTED"),"preferences":self.repo.get_preferences(uid)}
                    if method=="PUT":
                        previous=self.repo.get_preferences(uid); prefs=self.repo.save_preferences(uid,data); self.repo.set_onboarding_status(uid,"COMPLETED")
                        pipeline=self._preferences_updated(uid,previous,prefs,onboarding=True)
                        return 200,{"status":"COMPLETED","preferences":prefs,"generation":{"status":"SCHEDULED" if pipeline.get("scheduled") else pipeline.get("reason")}}
                if parts==["api","v1","me","briefings","today"] and method=="GET": return 200,self._client_briefing(uid,self.orchestrator._local_date(self.repo.get_preferences(uid)))
                if len(parts)==6 and parts[:4]==["api","v1","me","briefings"] and parts[5]=="progress" and method=="PUT":
                    from .scheduling import ensure_phase42_schema
                    ensure_phase42_schema(self.repo)
                    delivery=self.repo.db.execute("SELECT id FROM user_briefing_deliveries WHERE id=? AND user_id=?",(unquote(parts[4]),uid)).fetchone()
                    if not delivery: return self._error("RESOURCE_NOT_FOUND","briefing not found",request_id,404)
                    try: position=float(data.get("progress_seconds")); duration=float(data.get("duration_seconds"))
                    except (TypeError,ValueError): return self._error("VALIDATION_ERROR","progress and duration must be numbers",request_id,400)
                    if position<0 or duration<=0 or position>duration+1: return self._error("VALIDATION_ERROR","invalid listening progress",request_id,400)
                    position=min(position,duration); completed=position>=duration*.95; updated=now_iso()
                    self.repo.db.execute("""INSERT INTO briefing_listening_progress(delivery_id,user_id,progress_seconds,duration_seconds,completed_at,updated_at)
                        VALUES(?,?,?,?,?,?) ON CONFLICT(delivery_id,user_id) DO UPDATE SET progress_seconds=excluded.progress_seconds,
                        duration_seconds=excluded.duration_seconds,completed_at=COALESCE(briefing_listening_progress.completed_at,excluded.completed_at),updated_at=excluded.updated_at""",
                        (delivery["id"],uid,position,duration,updated if completed else None,updated)); self.repo.db.commit()
                    return 200,{"status":"saved","completed":completed}
                # Internal/admin compatibility endpoints only. The mobile client and
                # standard user flows must use scheduled deliveries instead.
                if parts==["api","v1","me","briefings","refresh"] and method=="POST":
                    from .scheduling import ensure_phase42_schema
                    ensure_phase42_schema(self.repo)
                    prefs=self.repo.get_preferences(uid)
                    if not prefs or (prefs.get("content_scope", "selected") != "all" and not prefs.get("topics")):
                        return self._error("PREFERENCES_INCOMPLETE","configure topics before refreshing",request_id,409)
                    active=self.repo.db.execute("SELECT id,status,stage FROM manual_refresh_requests WHERE user_id=? AND status IN ('PENDING','GENERATING') ORDER BY requested_at DESC LIMIT 1",(uid,)).fetchone()
                    if active: return 202,{"generation_id":active["id"],"reason":"MANUAL_REFRESH","status":active["status"],"stage":active["stage"],"coalesced":True}
                    generation_id="generation_"+uuid.uuid4().hex; requested=now_iso()
                    self.repo.db.execute("INSERT INTO manual_refresh_requests(id,user_id,reason,status,stage,requested_at,updated_at,selected_voice_id) VALUES(?,?,?,'PENDING','QUEUED',?,?,?)",(generation_id,uid,"MANUAL_REFRESH",requested,requested,prefs.get("audio_voice_id")))
                    self.repo.db.commit()
                    return 202,{"generation_id":generation_id,"reason":"MANUAL_REFRESH","status":"PENDING","stage":"QUEUED","coalesced":False}
                if len(parts)==6 and parts[:5]==["api","v1","me","briefings","generations"] and method=="GET":
                    row=self.repo.db.execute("SELECT * FROM manual_refresh_requests WHERE id=? AND user_id=?",(parts[5],uid)).fetchone()
                    if not row: return self._error("RESOURCE_NOT_FOUND","generation not found",request_id,404)
                    audio_status=None
                    if row["edition_id"]:
                        metadata=self.audio.audio_for_edition(row["edition_id"],voice=row["selected_voice_id"])
                        audio_status=metadata.get("status")
                    ingestion=self.repo.db.execute("SELECT * FROM content_ingestion_runs WHERE id=?",(row["ingestion_run_id"],)).fetchone() if row["ingestion_run_id"] else None
                    ingestion_summary={"run_id":ingestion["id"],"status":ingestion["status"],"started_at":ingestion["started_at"],"completed_at":ingestion["completed_at"],"sources_attempted":ingestion["sources_attempted"],"sources_successful":ingestion["sources_successful"],"articles_seen":ingestion["articles_seen"],"articles_new":ingestion["articles_new"],"articles_updated":ingestion["articles_updated"],"articles_unchanged":ingestion["articles_unchanged"],"source_errors":len(json.loads(ingestion["errors_json"] or "{}"))} if ingestion else None
                    safe_message=("A atualização falhou durante a etapa de áudio." if audio_status=="FAILED" else "A atualização não foi concluída. Tente novamente mais tarde.") if row["status"]=="FAILED" else None
                    return 200,{"generation_id":row["id"],"reason":row["reason"],"status":row["status"],"stage":row["stage"],"requested_at":row["requested_at"],"started_at":row["started_at"],"updated_at":row["updated_at"],"ingestion_run_id":row["ingestion_run_id"],"ingestion":ingestion_summary,"edition_id":row["edition_id"],"content_ready":bool(row["edition_id"]),"audio_status":audio_status,"audio_job_id":row["audio_job_id"],"selected_voice_id":row["selected_voice_id"],"audio_variant_id":row["audio_variant_id"],"error_code":row["error_code"],"error_message_safe":safe_message,"ready_at":row["finished_at"] if row["status"]=="READY" else None}
                if len(parts)==8 and parts[:5]==["api","v1","me","briefings","generations"] and parts[6:]==["audio","retry"] and method=="POST":
                    row=self.repo.db.execute("SELECT * FROM manual_refresh_requests WHERE id=? AND user_id=?",(parts[5],uid)).fetchone()
                    if not row or not row["edition_id"]: return self._error("RESOURCE_NOT_FOUND","generation audio not found",request_id,404)
                    if row["status"]!="FAILED": return self._error("GENERATION_NOT_FAILED","audio retry is only available after a failed generation",request_id,409)
                    edition=self.repo.db.execute("SELECT language FROM briefing_editions WHERE id=? AND status='READY'",(row["edition_id"],)).fetchone()
                    if not edition: return self._error("EDITION_NOT_READY","edition is not ready",request_id,409)
                    result=self.audio.retry(row["edition_id"],edition["language"],row["selected_voice_id"])
                    job=self.repo.db.execute("SELECT id FROM audio_generation_jobs WHERE edition_id=? AND voice=? ORDER BY created_at DESC LIMIT 1",(row["edition_id"],row["selected_voice_id"])).fetchone()
                    self.repo.db.execute("UPDATE manual_refresh_requests SET status='GENERATING',stage='AUDIO_QUEUED',audio_job_id=?,audio_variant_id=NULL,error_code=NULL,error_message=NULL,finished_at=NULL,updated_at=? WHERE id=?",(job["id"] if job else None,now_iso(),row["id"])); self.repo.db.commit()
                    return 202,{"generation_id":row["id"],"status":"GENERATING","stage":"AUDIO_QUEUED","audio_status":result.get("status"),"audio_job_id":job["id"] if job else None}
                if parts==["api","v1","me","briefings"] and method=="GET":
                    query=path.split("?",1)[1] if "?" in path else ""; params=dict(x.split("=",1) for x in query.split("&") if "=" in x); limit=max(1,min(int(params.get("limit",20)),50)); offset=int(params.get("cursor",0)); page,next_cursor=self._client_history(uid,limit,offset,include_audio=True); return 200,{"items":page,"next_cursor":next_cursor}
                if len(parts)==6 and parts[:4]==["api","v1","me","briefings"] and parts[5]=="audio" and method=="GET":
                    edition_id=self._edition_for_briefing(uid,parts[4])
                    if not edition_id: return self._error("RESOURCE_NOT_FOUND","briefing not found",request_id,404)
                    delivery=self.repo.db.execute("SELECT * FROM user_briefing_deliveries WHERE id=? AND user_id=?",(parts[4],uid)).fetchone()
                    language=self.repo.db.execute("SELECT language FROM briefing_editions WHERE id=?",(edition_id,)).fetchone()["language"]
                    preferred=(delivery["selected_voice_id"] if delivery and delivery["selected_voice_id"] else self.repo.get_preferences(uid).get("audio_voice_id"))
                    requested=self.audio.effective_voice(preferred,language)
                    active=delivery["active_voice_id"] if delivery else None
                    voice=active or requested
                    if self.config.audio_enabled and voice:
                        result=self.audio.audio_for_artifact(delivery["audio_artifact_id"]) if delivery and delivery["audio_artifact_id"] else {"status":delivery["audio_status"] if delivery and delivery["audio_status"] else "NOT_AVAILABLE"}
                        if delivery and delivery["audio_artifact_id"] and result.get("status")!="READY":
                            queued=self.audio.audio_for_edition(edition_id,language,voice)
                            if queued.get("status") in {"PENDING","GENERATING","VALIDATING"}: result=queued
                    else: result={"status":"NOT_AVAILABLE"}
                    result["selected_voice_id"]=preferred; result["active_voice_id"]=active; result["voice_fallback_reason"]=delivery["voice_fallback_reason"] if delivery else None
                    result["active_audio_variant_id"]=delivery["audio_artifact_id"] if delivery else result.get("artifact_id")
                    result["audio_duration_ms"]=result.get("duration_ms")
                    result["audio_status"]=delivery["audio_status"] if delivery else result.get("status")
                    result["generation_stage"]=delivery["generation_stage"] if delivery else result.get("generation_stage")
                    result["generation_started_at"]=delivery["generation_started_at"] if delivery else None
                    result["generation_updated_at"]=delivery["generation_updated_at"] if delivery else None
                    result["generation_error_code"]=delivery["generation_error_code"] if delivery else result.get("error_code")
                    if result.get("status")=="READY" and delivery and delivery["audio_artifact_id"] and result.get("artifact_id")!=delivery["audio_artifact_id"]:
                        result={**result,"status":"NOT_AVAILABLE","error_code":"DELIVERY_AUDIO_MISMATCH"}
                    if result.get("status")=="READY": result["audio_url"]="/api/v1/me/briefings/"+parts[4]+"/audio/file?v="+result["asset_version"]+"&voice="+voice
                    return 200,result
                if len(parts)==7 and parts[:4]==["api","v1","me","briefings"] and parts[5:]==["audio","retry"] and method=="POST":
                    delivery=self.repo.db.execute("SELECT * FROM user_briefing_deliveries WHERE id=? AND user_id=?",(parts[4],uid)).fetchone()
                    if not delivery: return self._error("RESOURCE_NOT_FOUND","briefing not found",request_id,404)
                    edition=self.repo.db.execute("SELECT language,status FROM briefing_editions WHERE id=?",(delivery["edition_id"],)).fetchone()
                    if not edition or edition["status"]!="READY": return self._error("EDITION_NOT_READY","edition is not ready",request_id,409)
                    voice=delivery["selected_voice_id"] or (self.repo.get_preferences(uid) or {}).get("audio_voice_id")
                    try: result=self.audio.retry(delivery["edition_id"],edition["language"],voice)
                    except Exception as exc:
                        from .audio import PermanentAudioError
                        if isinstance(exc,PermanentAudioError): return self._error(exc.code,str(exc),request_id,409)
                        raise
                    return 202,{"delivery_id":delivery["id"],"edition_id":delivery["edition_id"],"status":result.get("status"),"audio_status":result.get("status"),"stage":"AUDIO_QUEUED","selected_voice_id":voice}
                if len(parts)==7 and parts[:4]==["api","v1","me","briefings"] and parts[5:]==["audio","file"] and method=="GET":
                    edition_id=self._edition_for_briefing(uid,parts[4]); prefs=self.repo.get_preferences(uid)
                    requested_voice=parse_qs(path.split("?",1)[1]).get("voice",[None])[0] if "?" in path else None
                    requested_version=parse_qs(path.split("?",1)[1]).get("v",[None])[0] if "?" in path else None
                    language=self.repo.db.execute("SELECT language FROM briefing_editions WHERE id=?",(edition_id,)).fetchone()["language"] if edition_id else prefs["language"]
                    available={voice["id"] for voice in self.audio.available_voices(language)}
                    available.add(self.audio.default_voice(language))
                    if requested_voice and requested_voice not in available:
                        return self._error("RESOURCE_NOT_FOUND","audio not available",request_id,404)
                    voice=requested_voice or self.audio.effective_voice(prefs.get("audio_voice_id"),language)
                    delivery=self.repo.db.execute("SELECT * FROM user_briefing_deliveries WHERE id=? AND user_id=?",(parts[4],uid)).fetchone()
                    result=self.audio.audio_for_artifact(delivery["audio_artifact_id"]) if delivery and delivery["audio_artifact_id"] and self.config.audio_enabled else self.audio.audio_for_edition(edition_id,voice=voice) if edition_id and self.config.audio_enabled and voice else {"status":"NOT_AVAILABLE"}
                    if result.get("status")!="READY": return self._error("RESOURCE_NOT_FOUND","audio not ready",request_id,404)
                    if delivery and delivery["audio_artifact_id"] and (delivery["active_voice_id"]!=result.get("voice") or requested_voice!=delivery["active_voice_id"] or requested_version!=result.get("asset_version")):
                        return self._error("RESOURCE_NOT_FOUND","audio variant is no longer active",request_id,404)
                    if result.get("mime_type") not in {"audio/wav", "audio/mpeg", "audio/mp4", "audio/aac"}: return self._error("RESOURCE_NOT_FOUND","audio not available",request_id,404)
                    audio_path=self.audio.storage.resolve(self.repo.db.execute("SELECT storage_path FROM audio_artifacts WHERE id=?",(delivery["audio_artifact_id"],)).fetchone()["storage_path"]) if delivery and delivery["audio_artifact_id"] else self.audio.artifact_path(edition_id,voice=voice)
                    if not audio_path: return self._error("RESOURCE_NOT_FOUND","audio not available",request_id,404)
                    return 200,{"_audio_path":str(audio_path),"mime_type":result["mime_type"]}
                if len(parts)==5 and parts[:4]==["api","v1","me","briefings"] and method=="GET":
                    bid=parts[4]; delivery=self.repo.db.execute("SELECT * FROM user_briefing_deliveries WHERE id=? AND user_id=?",(bid,uid)).fetchone()
                    if delivery:
                        from .scheduling import serialize_edition
                        edition=serialize_edition(self.repo,delivery["edition_id"]); return 200,{"id":delivery["id"],"date":delivery["local_date"],"status":delivery["status"],"generated_at":(edition or {}).get("generated_at"),"items":(edition or {}).get("items",[])}
                    row=self.repo.db.execute("SELECT * FROM briefings WHERE id=? AND user_id=?",(bid,uid)).fetchone(); return (200,self.repo.serialize_briefing(row)) if row else self._error("RESOURCE_NOT_FOUND","briefing not found",request_id,404)
            if len(parts)>=4 and parts[:3]==["api","v1","users"]:
                uid=parts[3]
                if identity and uid!=identity.user_id: return self._error("FORBIDDEN","resource access denied",request_id,403)
                if method=="GET" and len(parts)==4: result=self.repo.public_user(self.repo.get_user(uid)); return (200,result) if result else self._error("RESOURCE_NOT_FOUND","user not found",request_id,404)
                if len(parts)>=5 and parts[4]=="preferences":
                    if method=="GET": return 200,self.repo.get_preferences(uid) or self._error("RESOURCE_NOT_FOUND","preferences not found",request_id,404)
                    if method=="PUT": return 200,self.repo.save_preferences(uid,data)
                if len(parts)>=5 and parts[4]=="briefings":
                    if len(parts)==5 and method=="GET": return 200,{"items":self.repo.list_briefings(uid)}
                    if len(parts)==6 and parts[5]=="today" and method=="GET": return 200,self._client_briefing(uid,self.orchestrator._local_date(self.repo.get_preferences(uid)))
                    if len(parts)==6 and method=="GET":
                        row=self.repo.db.execute("SELECT * FROM briefings WHERE id=? AND user_id=?",(parts[5],uid)).fetchone(); return (200,self.repo.serialize_briefing(row)) if row else self._error("RESOURCE_NOT_FOUND","briefing not found",request_id,404)
            # The environment snapshot is normally created at process startup. The
            # explicit runtime check also keeps tests/embedders that mutate env after
            # constructing a repository from accidentally exposing DEV routes.
            runtime_env=str(os.getenv("APP_ENV", self.config.app_env)).strip().lower()
            runtime_dev=os.getenv("ENABLE_DEV_ENDPOINTS")
            dev_allowed=self.config.dev_endpoints_enabled and runtime_env != "production" and str(runtime_dev or "true").lower() not in {"0","false","no","off"}
            if parts[:4]==["api","v1","dev","jobs"]:
                if not dev_allowed: return self._error("RESOURCE_NOT_FOUND","not found",request_id,404)
                return 200,{"items":[dict(x) for x in self.repo.db.execute("SELECT * FROM generation_jobs ORDER BY created_at DESC")],"count":self.repo.db.execute("SELECT COUNT(*) FROM generation_jobs").fetchone()[0]}
            if len(parts)==7 and parts[:4]==["api","v1","dev","users"] and parts[5:]==["briefing","diagnostic"] and method=="GET":
                if not dev_allowed or not identity or identity.user_id!=parts[4]: return self._error("RESOURCE_NOT_FOUND","not found",request_id,404)
                from .content import candidate_counts, ensure_content_schema
                from .scheduling import BriefingProfile
                from newzi_engine.topic_registry import taxonomy
                ensure_content_schema(self.repo)
                raw=self.repo.db.execute("SELECT topics_json FROM user_preferences WHERE user_id=?",(parts[4],)).fetchone()
                canonical,unknown=taxonomy().canonicalize(json.loads(raw["topics_json"]) if raw else [])
                profile=BriefingProfile.from_preferences(self.repo.get_preferences(parts[4])); local_date=self.orchestrator._local_date(self.repo.get_preferences(parts[4]))
                job=self.repo.db.execute("SELECT status,error_code,error_message FROM generation_jobs WHERE user_id=? AND briefing_date=?",(parts[4],local_date)).fetchone()
                edition=self.repo.db.execute("SELECT e.status,e.item_count FROM briefing_editions e JOIN user_briefing_deliveries d ON d.edition_id=e.id WHERE d.user_id=? AND d.local_date=?",(parts[4],local_date)).fetchone()
                fallback=[]; diagnostic_items=[]
                for item in self.repo.db.execute("""SELECT i.event_id,i.sources_json,i.warnings_json,i.primary_taxonomy_id,
                    i.primary_taxonomy_label,i.primary_taxonomy_reason,i.matched_taxonomy_ids_json,i.user_interest_matches_json
                    FROM briefing_edition_items i JOIN user_briefing_deliveries d ON d.edition_id=i.edition_id
                    WHERE d.user_id=? AND d.local_date=? ORDER BY i.position""",(parts[4],local_date)):
                    fallback.extend(w for w in json.loads(item["warnings_json"]) if isinstance(w,str) and w.startswith("FALLBACK_"))
                    sources=json.loads(item["sources_json"])
                    diagnostic_items.append({"content_id":sources[0].get("article_id") if sources else item["event_id"],
                        "matched_taxonomy_ids":json.loads(item["matched_taxonomy_ids_json"] or "[]"),
                        "user_interest_matches":json.loads(item["user_interest_matches_json"] or "[]"),
                        "primary_taxonomy_id":item["primary_taxonomy_id"],"primary_taxonomy_label":item["primary_taxonomy_label"],
                        "primary_taxonomy_reason":item["primary_taxonomy_reason"]})
                return 200,{"effective_canonical_taxonomy_ids":canonical,"unknown_taxonomy_ids":unknown,"profile_key":profile.key(),**candidate_counts(self.repo,canonical),"edition_status":edition["status"] if edition else None,"job_status":job["status"] if job else None,"last_error":job["error_code"] if job else None,"fallback_levels":sorted(set(fallback)),"items":diagnostic_items,"pipeline":self._pipeline_diagnostic(parts[4])}
            if parts==["api","v1","dev","scheduler","run"]:
                if not dev_allowed: return self._error("RESOURCE_NOT_FOUND","not found",request_id,404)
                return 200,self.scheduler.run_once()
            if parts==["api","v1","dev","worker","run"]:
                if not dev_allowed: return self._error("RESOURCE_NOT_FOUND","not found",request_id,404)
                return 200,self.worker.run_once()
            if parts==["api","v1","dev","audio","run"] and method=="POST":
                if not dev_allowed: return self._error("RESOURCE_NOT_FOUND","not found",request_id,404)
                return 200,self.audio.generate_pending()
            if parts==["api","v1","dev","audio","metrics"] and method=="GET":
                if not dev_allowed: return self._error("RESOURCE_NOT_FOUND","not found",request_id,404)
                return 200,self.audio.metrics()
            if parts==["api","v1","dev","notifications","enqueue"] and method=="POST":
                if not dev_allowed: return self._error("RESOURCE_NOT_FOUND","not found",request_id,404)
                return 200,self.notifications.enqueue_ready()
            if parts==["api","v1","dev","notifications","run"] and method=="POST":
                if not dev_allowed: return self._error("RESOURCE_NOT_FOUND","not found",request_id,404)
                return 200,self.notifications.run_once()
            if len(parts)==7 and parts[:4]==["api","v1","dev","briefings"] and parts[5:]==["audio","generate"] and method=="POST":
                if not dev_allowed: return self._error("RESOURCE_NOT_FOUND","not found",request_id,404)
                edition_id=parts[4]
                if not self.repo.db.execute("SELECT id FROM briefing_editions WHERE id=?",(edition_id,)).fetchone():
                    delivery=self.repo.db.execute("SELECT edition_id FROM user_briefing_deliveries WHERE id=?",(edition_id,)).fetchone(); edition_id=delivery["edition_id"] if delivery else None
                return 202,self.audio.request(edition_id) if edition_id else self._error("RESOURCE_NOT_FOUND","briefing not found",request_id,404)
            if method=="POST" and len(parts)==7 and parts[:4]==["api","v1","dev","users"] and parts[5]=="briefings" and parts[6]=="generate":
                if not dev_allowed: return self._error("RESOURCE_NOT_FOUND","not found",request_id,404)
                result,mode=self.orchestrator.generate(parts[4]); return 200,{"mode":mode,"briefing":result}
            return self._error("RESOURCE_NOT_FOUND","not found",request_id,404)
        except ValueError as exc: return self._error("VALIDATION_ERROR",str(exc),request_id,400)
        except Exception as exc:
            if self.config.app_env == "development": log.exception("product api request failed", extra={"request_id":request_id})
            return self._error("INTERNAL_ERROR","internal error",request_id,500)


def seed_dev(path=None): return ProductRepository(path).create_dev_user()

