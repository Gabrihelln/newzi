"""Product backend: configuration, persistence and the use cases behind the HTTP API.

Product data lives in its own database (SQLite by default, PostgreSQL via DATABASE_URL),
separate from the engine's collection cache. ``ProductRepository`` owns the connection and
the user-facing data; ``ProductService`` implements each API operation independently of the
web framework (see ``newzi_backend.api`` for the FastAPI routes).
"""
import json, logging, os, re, threading, time, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from newzi_engine.topic_registry import SUPPORTED_TOPIC_IDS, TOPIC_LABELS, topic_rows, taxonomy
from newzi_engine.utils.text import strip_junk_text
from . import db as database
from .migrations import migrate
from .paths import BACKEND_DATA, PROJECT_ROOT

TOPICS = {code: TOPIC_LABELS[code] for code in SUPPORTED_TOPIC_IDS}
STATUSES = {"PENDING", "GENERATING", "READY", "PARTIAL", "FAILED"}
ALLOWED_ENVIRONMENTS = {"development", "staging", "production"}
log = logging.getLogger("news_engine.product")


from .timeutil import iso, now_iso, parse


class ProductConfig:
    def __init__(self, environ=None):
        env = environ if environ is not None else os.environ
        self.app_env = str(env.get("APP_ENV", "development")).strip().lower()
        if self.app_env not in ALLOWED_ENVIRONMENTS:
            raise ValueError("APP_ENV must be development, staging, or production")
        raw = env.get("DATABASE_URL", f"sqlite:///{(BACKEND_DATA / 'product_backend.sqlite3').as_posix()}")
        self.database_url = raw
        self.database_dialect = database.dialect_for(raw)
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
    base = {"topics": [row["id"] for row in topic_rows() if row["enabled"]][:3], "content_scope": "selected", "language": "pt-BR", "country_scope": "BOTH", "briefing_time": "06:00", "timezone": "America/Sao_Paulo", "briefing_size": 10, "audio_enabled": False, "audio_voice_id": None, "briefing_length": "standard"}
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
    base["briefing_length"]=base.get("briefing_length") or "standard"
    if base["briefing_length"] not in {"standard", "extended"}: raise ValueError("briefing_length must be standard or extended")
    from .audio import VOICE_CATALOG
    known_voices={voice["id"] for voices in VOICE_CATALOG.values() for voice in voices}
    if base["audio_voice_id"] is not None and base["audio_voice_id"] not in known_voices: raise ValueError("unsupported audio_voice_id")
    validate_timezone(base["timezone"]); validate_briefing_time(base["briefing_time"])
    return base


def local_date_for(prefs, clock=None):
    """The user's current calendar date in their own timezone."""
    now = clock.now(prefs["timezone"]) if clock else datetime.now(ZoneInfo(prefs["timezone"]))
    return now.date().isoformat()


def _story_topic(story, registry):
    raw = story.get("primary_taxonomy_id") or story.get("primary_taxonomy_label") or story.get("category")
    return registry.resolve(raw) if raw else None


class ProductRepository:
    def __init__(self, path=None, config=None):
        self.config = config or ProductConfig()
        self.dialect = self.config.database_dialect if path is None else database.SQLITE
        self.path = Path(path or self.config.db_path)
        if self.dialect == database.SQLITE: self.path.parent.mkdir(parents=True, exist_ok=True)
        # One connection per thread: concurrent requests must never interleave transactions.
        self._local = threading.local(); self._synced_taxonomy = None
        migrate(self.db); self.sync_taxonomy()

    @property
    def db(self):
        connection = getattr(self._local, "db", None)
        if connection is None:
            connection = database.connect(self.config.database_url, sqlite_path=self.path)
            self._local.db = connection
        return connection

    def close_thread_connection(self):
        """Close the calling thread's connection (rolling back anything left uncommitted)."""
        connection = getattr(self._local, "db", None)
        if connection is not None:
            self._local.db = None
            try: connection.rollback()
            finally: connection.close()

    def release_thread_connection(self):
        """End the calling thread's open transaction, keeping the connection for reuse."""
        connection = getattr(self._local, "db", None)
        if connection is not None and connection.in_transaction:
            connection.rollback()

    def sync_taxonomy(self):
        registry = taxonomy()
        for node in registry.nodes.values():
            self.db.execute("INSERT INTO topics(code,name,active,slug,parent_id,type) VALUES(?,?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET name=excluded.name,active=excluded.active,slug=excluded.slug,parent_id=excluded.parent_id,type=excluded.type", (node["id"],node["name"],int(node.get("active",True)),node.get("slug"),node.get("parent_id"),node.get("type","subject")))
            for alias in node.get("aliases", []):
                self.db.execute("INSERT INTO taxonomy_aliases(alias,code) VALUES(?,?) ON CONFLICT(alias) DO UPDATE SET code=excluded.code",(alias,node["id"]))
        self.db.commit(); self._synced_taxonomy = registry

    def _sync_taxonomy_if_changed(self):
        # taxonomy() returns a new object only when the taxonomy file changed.
        if taxonomy() is not self._synced_taxonomy: self.sync_taxonomy()

    def create_dev_user(self):
        uid = "dev-user-001"; t = now_iso(); self.db.execute("INSERT INTO users(id,email,display_name,language,timezone,created_at,updated_at,status,onboarding_status) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING", (uid, "dev@newzi.local", "Newzi Dev", self.config.default_language, self.config.default_timezone, t, t, "ACTIVE", "COMPLETED")); self.db.execute("""INSERT INTO user_preferences
            (user_id,topics_json,language,country_scope,briefing_time,timezone,briefing_size,audio_enabled,updated_at,audio_voice_id)
            VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO NOTHING""", (uid, json.dumps([row["id"] for row in topic_rows() if row["enabled"]][:3]), "pt-BR", "BOTH", "06:00", "America/Sao_Paulo", 10, 0, t, None)); self.db.commit(); return self.get_user(uid)

    def get_user(self, uid):
        row=self.db.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone(); return dict(row) if row else None
    def ensure_firebase_user(self, firebase_uid, email, display_name="", account_exists=None):
        """The user row of a verified Firebase account, created on its first request.

        ``account_exists(firebase_uid)`` tells whether another Firebase account still exists; it decides
        whether a row holding this e-mail belongs to an account deleted outside the app.
        """
        existing = self.db.execute("SELECT * FROM users WHERE firebase_uid=? OR id=?", (firebase_uid, firebase_uid)).fetchone()
        t = now_iso()
        if existing:
            wanted = (firebase_uid, email or existing["email"], display_name or existing["display_name"])
            # Runs on every authenticated request: only write when the token's profile changed.
            if wanted != (existing["firebase_uid"], existing["email"], existing["display_name"]):
                self.db.execute("UPDATE users SET firebase_uid=?,email=?,display_name=?,updated_at=? WHERE id=?", (*wanted, t, existing["id"]))
                self.db.commit()
            if not self.get_preferences(existing["id"]): self.save_preferences(existing["id"], {})
            return dict(existing) if wanted == (existing["firebase_uid"], existing["email"], existing["display_name"]) else self.get_user(existing["id"])
        # An account deleted in the Firebase console keeps its row here; the same e-mail signing up
        # again gets a new UID and would hit the unique e-mail forever. That row and its data go.
        holder = self.db.execute("SELECT id,firebase_uid FROM users WHERE email=? AND email<>''", (email or "",)).fetchone()
        if holder and account_exists and not account_exists(holder["firebase_uid"] or holder["id"]):
            log.info("[Backend Auth] stale_account_removed=true")
            self.delete_user(holder["id"])
        # The app's first screen sends several requests at once; the ones that lose the race to
        # create the row use it instead of failing on the unique UID.
        self.db.execute("INSERT INTO users(id,firebase_uid,email,display_name,language,timezone,created_at,updated_at,status,onboarding_status) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING", (firebase_uid, firebase_uid, email or "", display_name or "", self.config.default_language, self.config.default_timezone, t, t, "ACTIVE", "NOT_STARTED"))
        self.db.commit()
        created = self.db.execute("SELECT * FROM users WHERE firebase_uid=? OR id=?", (firebase_uid, firebase_uid)).fetchone()
        if not created:
            # The e-mail belongs to another live account (it cannot under Firebase's one-account-per-
            # e-mail rule, but never attach one person's data to another).
            log.warning("[Backend Auth] user_row_conflict=true reason=EMAIL_IN_USE")
            return None
        if not self.get_preferences(created["id"]): self.save_preferences(created["id"], {})
        return dict(created)
    @staticmethod
    def public_user(user):
        if not user: return None
        out={k:user.get(k) for k in ("id","email","display_name","language","timezone","created_at","updated_at","status","onboarding_status") if k in user}
        from .avatars import photo_url
        if photo_url(user): out["photo_url"]=photo_url(user)
        return out
    @staticmethod
    def _preferences_from_row(row):
        out=dict(row); out["topics"]=list(taxonomy().canonicalize(json.loads(out.pop("topics_json")))[0]); out["audio_enabled"]=bool(out["audio_enabled"]); out.setdefault("content_scope", "selected"); return out
    def get_preferences(self, uid):
        row=self.db.execute("SELECT * FROM user_preferences WHERE user_id=?",(uid,)).fetchone()
        return self._preferences_from_row(row) if row else None
    def active_preferences(self):
        """``(user_id, preferences)`` for every active user, in one query."""
        return [(row["user_id"], self._preferences_from_row(row)) for row in self.db.execute(
            "SELECT p.* FROM user_preferences p JOIN users u ON u.id=p.user_id WHERE u.status='ACTIVE' ORDER BY p.user_id")]
    def save_preferences(self, uid, data):
        if "topics" in data:
            registry=taxonomy()
            alias_count=sum(bool(registry.resolve(value)) and value != registry.resolve(value) for value in data["topics"])
            unknown_count=sum(not registry.resolve(value) for value in data["topics"])
            for name, count in (("taxonomy_alias_resolutions",alias_count),("taxonomy_unknown_ids",unknown_count)):
                if count: self.db.execute("INSERT INTO taxonomy_resolution_metrics(name,count) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET count=taxonomy_resolution_metrics.count+excluded.count",(name,count))
            if alias_count or unknown_count: self.db.commit()
        prefs=validate_preferences(data, self.get_preferences(uid) or {}); t=now_iso(); self.db.execute("""INSERT INTO user_preferences
            (user_id,topics_json,language,country_scope,briefing_time,timezone,briefing_size,audio_enabled,updated_at,audio_voice_id,content_scope,briefing_length)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET topics_json=excluded.topics_json,language=excluded.language,
            country_scope=excluded.country_scope,briefing_time=excluded.briefing_time,timezone=excluded.timezone,briefing_size=excluded.briefing_size,
            audio_enabled=excluded.audio_enabled,updated_at=excluded.updated_at,audio_voice_id=excluded.audio_voice_id,content_scope=excluded.content_scope,
            briefing_length=excluded.briefing_length""",
            (uid,json.dumps(prefs["topics"]),prefs["language"],prefs["country_scope"],prefs["briefing_time"],prefs["timezone"],prefs["briefing_size"],int(prefs["audio_enabled"]),t,prefs["audio_voice_id"],prefs["content_scope"],prefs.get("briefing_length") or "standard")); self.db.commit(); return self.get_preferences(uid)
    def set_onboarding_status(self, uid, status):
        self.db.execute("UPDATE users SET onboarding_status=?,updated_at=? WHERE id=?",(status,now_iso(),uid)); self.db.commit()
    def list_topics(self):
        self._sync_taxonomy_if_changed()
        active={row["code"] for row in self.db.execute("SELECT code FROM topics WHERE active=1")}
        counts={row["taxonomy_id"]:row["count"] for row in self.db.execute("SELECT taxonomy_id,COUNT(DISTINCT content_id) AS count FROM content_taxonomy GROUP BY taxonomy_id")}
        return [{**row,"content_count":counts.get(row["code"],0)} for row in topic_rows() if row["code"] in active and row["enabled"]]

    def latest_news(self, uid, limit=20, topic=None, query=None, discovery=False):
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
        # Only stories with a picture are listed (Home, Explore, topics and search); an event whose best article has
        # no image is shown through one of its other articles that has one.
        clauses=["c.published_at IS NOT NULL","c.image_url LIKE 'http%'"]
        where_params=[]
        # A real publication date older than this freshness horizon is not a
        # Home/Explore candidate; ingestion time never substitutes for it.
        freshness_cutoff=iso(datetime.now(timezone.utc)-timedelta(days=30))
        clauses.append("c.published_at>=?");where_params.append(freshness_cutoff)
        from .content import world_source_ids
        if prefs.get("country_scope")=="LOCAL": clauses.append("c.source_country='BR'")
        elif prefs.get("country_scope")=="GLOBAL":
            # Internacional is world news: foreign outlets and the Brazilian outlets' world desks.
            world=sorted(world_source_ids())
            clauses.append("(c.source_country IS NULL OR c.source_country<>'BR'"+(" OR c.source_id IN ("+",".join("?" for _ in world)+")" if world else "")+")")
            where_params.extend(world)
        # Portuguese readers see Portuguese coverage only (content.readable): a story only in English is not listed.
        if str(prefs.get("language") or "pt-BR").lower().startswith("pt"):
            clauses.append("(c.source_language IS NULL OR c.source_language='' OR lower(c.source_language) LIKE 'pt%')")
        if selected_with_children:
            clauses.append("EXISTS (SELECT 1 FROM content_taxonomy interest WHERE interest.content_id=c.id AND interest.taxonomy_id IN ("+",".join("?" for _ in selected_with_children)+"))")
            where_params.extend(selected_with_children)
        if query:
            from .search import search_clause
            clause, params = search_clause(self.db, query)
            clauses.append(clause); where_params.extend(params)
        interest_params=[]
        interest_parts=[]
        if exact_ids:
            interest_parts.append("WHEN t.taxonomy_id IN ("+",".join("?" for _ in exact_ids)+") THEN 2")
            interest_params.extend(exact_ids)
        if selected_with_children:
            interest_parts.append("WHEN t.taxonomy_id IN ("+",".join("?" for _ in selected_with_children)+") THEN 1")
            interest_params.extend(selected_with_children)
        interest_case="MAX(CASE "+" ".join(interest_parts)+" ELSE 0 END)" if interest_parts else "0"
        primary_topic="(SELECT topic.taxonomy_id FROM content_taxonomy topic WHERE topic.content_id=c.id ORDER BY topic.score DESC,topic.taxonomy_id LIMIT 1)"
        reader_language=prefs.get("language") or "pt-BR"
        # Any variety of the reader's language counts as a match ("pt-PT" for a "pt-BR" reader).
        query_params=[*interest_params,reader_language.split("-")[0]+"%",*where_params,min(300,max(1,int(limit)*10))]
        sql=("WITH candidates AS (SELECT c.id,c.title,c.description,c.source_name,c.source_id,c.url,c.published_at,"
             "c.image_url,c.source_language,c.quality_score,COALESCE(NULLIF(c.event_id,''),c.id) AS event_key,"+interest_case+" AS interest_score,"
             "CASE WHEN c.source_language LIKE ? THEN 1 ELSE 0 END AS language_match,"+primary_topic+" AS primary_taxonomy_id ")
        sql += "FROM indexed_content c LEFT JOIN content_taxonomy t ON t.content_id=c.id WHERE "+" AND ".join(clauses)+" GROUP BY c.id), ranked AS (SELECT candidates.*,ROW_NUMBER() OVER(PARTITION BY event_key ORDER BY interest_score DESC,language_match DESC,published_at DESC,quality_score DESC,id) AS event_rank FROM candidates) SELECT * FROM ranked WHERE event_rank=1 ORDER BY published_at DESC,interest_score DESC,quality_score DESC,id LIMIT ?"
        from newzi_engine.images import canonical_image_url
        rows=[row for row in self.db.execute(sql,query_params).fetchall() if canonical_image_url(row["image_url"])]
        size=max(1,min(int(limit),30))
        now=datetime.now(timezone.utc)
        base_scores={}
        for row in rows:
            published=parse(row["published_at"])
            if published.tzinfo is None: published=published.replace(tzinfo=timezone.utc)
            age_days=max(0.0,(now-published).total_seconds()/86400)
            freshness=max(0.0,1.0-age_days/30.0)
            interest=float(row["interest_score"] or 0)/2.0
            language=float(row["language_match"] or 0)
            quality=max(0.0,min(1.0,float(row["quality_score"] or 0)/15.0))
            base_scores[row["id"]]=0.46*interest+0.30*freshness+0.14*language+0.10*quality
        source_counts={};chosen=[]
        remaining=list(rows)
        while remaining and len(chosen)<size:
            best=max(remaining,key=lambda row:(base_scores[row["id"]]-min(0.36,source_counts.get(row["source_id"],0)*0.12),row["published_at"],row["id"]))
            remaining.remove(best);source_counts[best["source_id"]]=source_counts.get(best["source_id"],0)+1
            chosen.append(best)
        # Relevance and source variety pick the stories; a feed is read newest first (a search keeps relevance).
        if not query: chosen.sort(key=lambda row:(row["published_at"],row["id"]),reverse=True)
        # Label by the user's interest (as briefings do), not by the article's strongest generic tag.
        tags_by_content={}
        if selected and chosen:
            from .content import primary_taxonomy
            ids=[row["id"] for row in chosen]
            for tag in self.db.execute("SELECT content_id,taxonomy_id,score FROM content_taxonomy WHERE content_id IN ("+",".join("?" for _ in ids)+")",ids):
                tags_by_content.setdefault(tag["content_id"],{})[tag["taxonomy_id"]]=tag["score"]
        output=[]
        for best in chosen:
            taxonomy_id=best["primary_taxonomy_id"]
            if selected:
                picked=primary_taxonomy(tags_by_content.get(best["id"],{}),sorted(selected),registry)
                if picked: taxonomy_id=picked["id"]
            label=registry.nodes.get(taxonomy_id,{}).get("name") if taxonomy_id else None
            output.append({"id":best["id"],"position":len(output)+1,"headline":best["title"],"summary":strip_junk_text(best["description"]) or best["title"],
                "category":label,"primary_taxonomy_id":taxonomy_id,"primary_taxonomy_label":label,"published_at":best["published_at"],
                "image_url":best["image_url"],"sources":[{"publisher":best["source_name"],"url":best["url"],"article_id":best["id"],"published_at":best["published_at"],"image_url":best["image_url"]}],"key_points":[]})
        return self._attach_event_sources(output)

    def story(self, uid, story_id):
        """One indexed story in the news-item shape, e.g. for a breaking-news push the user tapped."""
        row=self.db.execute("""SELECT c.*,(SELECT t.taxonomy_id FROM content_taxonomy t WHERE t.content_id=c.id ORDER BY t.score DESC,t.taxonomy_id LIMIT 1) AS primary_taxonomy_id
            FROM indexed_content c WHERE c.id=?""",(story_id,)).fetchone()
        if not row: return None
        registry=taxonomy(); taxonomy_id=row["primary_taxonomy_id"]
        selected=sorted((self.get_preferences(uid) or {}).get("topics") or [])
        if selected:
            from .content import primary_taxonomy
            tags={tag["taxonomy_id"]:tag["score"] for tag in self.db.execute("SELECT taxonomy_id,score FROM content_taxonomy WHERE content_id=?",(story_id,))}
            picked=primary_taxonomy(tags,selected,registry)
            if picked: taxonomy_id=picked["id"]
        label=registry.nodes.get(taxonomy_id,{}).get("name") if taxonomy_id else None
        item={"id":row["id"],"position":1,"headline":row["title"],"summary":strip_junk_text(row["description"]) or row["title"],
            "category":label,"primary_taxonomy_id":taxonomy_id,"primary_taxonomy_label":label,"published_at":row["published_at"],
            "image_url":row["image_url"],"sources":[{"publisher":row["source_name"],"url":row["url"],"article_id":row["id"],"published_at":row["published_at"],"image_url":row["image_url"]}],"key_points":[]}
        return self._attach_event_sources([item])[0]

    def _attach_event_sources(self, items, limit=5):
        """Credit the other outlets that covered each story's event, best first, one per publisher."""
        ids=[item["id"] for item in items]
        if not ids: return items
        own={row["id"]:row for row in self.db.execute("SELECT id,event_id,source_id FROM indexed_content WHERE id IN ("+",".join("?" for _ in ids)+")",ids)}
        events=sorted({row["event_id"] for row in own.values() if row["event_id"]})
        if not events: return items
        members={}
        for row in self.db.execute("SELECT id,event_id,source_id,source_name,url,published_at,image_url FROM indexed_content WHERE event_id IN ("+",".join("?" for _ in events)+") ORDER BY quality_score DESC,id",events):
            members.setdefault(row["event_id"],[]).append(row)
        for item in items:
            mine=own.get(item["id"])
            if not mine or not mine["event_id"]: continue
            publishers={mine["source_id"]}
            for row in members.get(mine["event_id"],[]):
                if len(item["sources"])>=limit: break
                if row["source_id"] in publishers: continue
                publishers.add(row["source_id"])
                item["sources"].append({"publisher":row["source_name"],"url":row["url"],"article_id":row["id"],"published_at":row["published_at"],"image_url":row["image_url"]})
        return items

    def _canonical_article_image(self, story):
        """Hydrate saved legacy snapshots from the article's single indexed image."""
        if not isinstance(story,dict) or not story.get("id"):
            return story
        source_rows=[source for source in story.get("sources",[]) if isinstance(source,dict)]
        article_ids=[story["id"],*(source.get("article_id") for source in source_rows if source.get("article_id"))]
        found={row["id"]:row["image_url"] for row in self.db.execute(
            "SELECT id,image_url FROM indexed_content WHERE id IN ("+",".join("?" for _ in article_ids)+") AND image_url IS NOT NULL",article_ids)}
        image_url=next((found[article_id] for article_id in article_ids if found.get(article_id)),None)
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

    _SAVED_SELECT = """SELECT s.story_json,s.saved_at,p.progress,p.updated_at AS progress_updated_at
            FROM saved_stories s LEFT JOIN saved_story_progress p ON p.user_id=s.user_id AND p.story_id=s.story_id
            WHERE s.user_id=? ORDER BY s.saved_at DESC,s.story_id"""

    def _saved_row(self, row):
        story=self._canonical_article_image(json.loads(row["story_json"]))
        story["saved_at"]=row["saved_at"]
        story["reading_progress"]=round(float(row["progress"] or 0),1)
        story["reading_updated_at"]=row["progress_updated_at"]
        return story

    def saved_stories(self, uid, limit=None, offset=0, topic_id=None):
        """Saved stories, newest first; returns ``(items, has_more)`` when ``limit`` is given."""
        start=max(0,int(offset or 0))
        if topic_id is None:
            # Pages are cut in SQL: only the requested rows are read and hydrated.
            if limit is None:
                return [self._saved_row(row) for row in self.db.execute(self._SAVED_SELECT,(uid,))]
            rows=self.db.execute(self._SAVED_SELECT+" LIMIT ? OFFSET ?",(uid,limit+1,start)).fetchall()
            return [self._saved_row(row) for row in rows[:limit]], len(rows)>limit
        # The topic of a snapshot is resolved through the current taxonomy, so filtering stays in Python.
        registry=taxonomy(); matched=[]
        for row in self.db.execute(self._SAVED_SELECT,(uid,)):
            canonical=_story_topic(json.loads(row["story_json"]),registry)
            if (not canonical) if topic_id=="__OTHER__" else canonical==topic_id:
                matched.append(row)
        if limit is None:
            return [self._saved_row(row) for row in matched[start:]]
        return [self._saved_row(row) for row in matched[start:start+limit]], start+limit<len(matched)

    def saved_story_progress(self, uid, story_id, progress):
        if not self.db.execute("SELECT 1 FROM saved_stories WHERE user_id=? AND story_id=?",(uid,story_id)).fetchone(): return False
        value=max(0.0,min(100.0,float(progress)))
        self.db.execute("INSERT INTO saved_story_progress(user_id,story_id,progress,updated_at) VALUES(?,?,?,?) ON CONFLICT(user_id,story_id) DO UPDATE SET progress=excluded.progress,updated_at=excluded.updated_at",(uid,story_id,value,now_iso()))
        self.db.commit(); return True

    def saved_overview(self, uid):
        registry=taxonomy()
        stories=self.db.execute(self._SAVED_SELECT,(uid,)).fetchall()
        counts={}; topic_order={node_id:node.get("display_order",0) for node_id,node in registry.nodes.items()}
        continue_reading=None
        progress_rows=self.db.execute("""SELECT s.story_json,s.saved_at,p.progress,p.updated_at AS progress_updated_at
            FROM saved_story_progress p JOIN saved_stories s ON s.user_id=p.user_id AND s.story_id=p.story_id
            WHERE p.user_id=? AND p.progress>0 AND p.progress<100 ORDER BY p.updated_at DESC LIMIT 1""",(uid,)).fetchone()
        if progress_rows:
            continue_reading=self._canonical_article_image(json.loads(progress_rows["story_json"]))
            continue_reading.update({"saved_at":progress_rows["saved_at"],"reading_progress":round(float(progress_rows["progress"]),1),"reading_updated_at":progress_rows["progress_updated_at"]})
        recent=[{"type":"article","saved_at":row["saved_at"],"item":self._canonical_article_image(json.loads(row["story_json"])),"reading_progress":round(float(row["progress"] or 0),1)} for row in stories[:12]]
        for row in self.db.execute("SELECT briefing_id,saved_at FROM saved_briefings WHERE user_id=? ORDER BY saved_at DESC LIMIT 12",(uid,)):
            briefing=self.briefing_for_user(uid,row["briefing_id"])
            if briefing: recent.append({"type":"briefing","saved_at":row["saved_at"],"briefing":briefing})
        recent.sort(key=lambda item:item.get("saved_at") or "",reverse=True)
        for row in stories:
            key=_story_topic(json.loads(row["story_json"]),registry) or "__OTHER__"
            counts[key]=counts.get(key,0)+1
        topics=[{"id":topic_id,"name":registry.nodes[topic_id]["name"],"count":count,"order":topic_order.get(topic_id,0)} for topic_id,count in counts.items() if topic_id!="__OTHER__"]
        topics.sort(key=lambda topic:(-topic["count"],topic["order"],topic["id"]))
        if counts.get("__OTHER__"):
            topics.append({"id":"__OTHER__","name":"Outros","count":counts["__OTHER__"],"order":10**9})
        from .collections import list_collections
        return {"saved_count":len(stories),"continue_reading":continue_reading,"topic_summary":topics,"recent_items":recent[:12],"collections":list_collections(self,uid)}

    def save_story(self, uid, story):
        clean=self._canonical_article_image(self._saved_story(story))
        self.db.execute("INSERT INTO saved_stories(user_id,story_id,story_json,saved_at) VALUES(?,?,?,?) ON CONFLICT(user_id,story_id) DO UPDATE SET story_json=excluded.story_json,saved_at=excluded.saved_at",(uid,clean["id"],json.dumps(clean,ensure_ascii=False),now_iso()))
        self.db.commit(); return clean

    def remove_saved_story(self, uid, story_id):
        # A story leaves its collections with Salvos.
        self.db.execute("DELETE FROM saved_collection_items WHERE user_id=? AND story_id=?",(uid,story_id))
        cursor=self.db.execute("DELETE FROM saved_stories WHERE user_id=? AND story_id=?",(uid,story_id)); self.db.commit(); return cursor.rowcount>0

    def article_feedback(self, uid, story_id, rating=None):
        if rating is not None:
            self.db.execute("INSERT INTO article_feedback(user_id,story_id,rating,updated_at) VALUES(?,?,?,?) ON CONFLICT(user_id,story_id) DO UPDATE SET rating=excluded.rating,updated_at=excluded.updated_at",(uid,story_id,rating,now_iso())); self.db.commit()
        row=self.db.execute("SELECT rating,updated_at FROM article_feedback WHERE user_id=? AND story_id=?",(uid,story_id)).fetchone()
        return {"rating":row["rating"],"updated_at":row["updated_at"]} if row else {"rating":None,"updated_at":None}

    def briefing_for_user(self, uid, briefing_id):
        delivery=self.db.execute("SELECT * FROM user_briefing_deliveries WHERE id=? AND user_id=?",(briefing_id,uid)).fetchone()
        if not delivery: return None
        from .scheduling import serialize_edition
        edition=serialize_edition(self,delivery["edition_id"])
        return {"id":delivery["id"],"date":delivery["local_date"],"status":delivery["status"],"generated_at":(edition or {}).get("generated_at"),"items":(edition or {}).get("items",[])}

    def save_briefing(self, uid, briefing_id):
        if not self.briefing_for_user(uid,briefing_id): return False
        self.db.execute("INSERT INTO saved_briefings(user_id,briefing_id,saved_at) VALUES(?,?,?) ON CONFLICT(user_id,briefing_id) DO UPDATE SET saved_at=excluded.saved_at",(uid,briefing_id,now_iso())); self.db.commit(); return True

    def saved_briefings(self, uid):
        result=[]
        for row in self.db.execute("SELECT briefing_id,saved_at FROM saved_briefings WHERE user_id=? ORDER BY saved_at DESC LIMIT 100",(uid,)):
            briefing=self.briefing_for_user(uid,row["briefing_id"])
            if briefing: briefing["saved_at"]=row["saved_at"]; result.append(briefing)
        return result

    def remove_saved_briefing(self, uid, briefing_id):
        cursor=self.db.execute("DELETE FROM saved_briefings WHERE user_id=? AND briefing_id=?",(uid,briefing_id)); self.db.commit(); return cursor.rowcount>0

    # Children before parents, in one transaction. Editions and audio are shared by profile, not personal.
    USER_DATA_DELETES = (
        "DELETE FROM generation_job_phases WHERE job_id IN (SELECT id FROM generation_jobs WHERE user_id=?)",
        "DELETE FROM notification_events WHERE device_id IN (SELECT id FROM push_devices WHERE user_id=?)",
        *(f"DELETE FROM {table} WHERE user_id=?" for table in (
            "saved_story_progress", "saved_stories", "article_feedback", "saved_briefings", "briefing_listening_progress",
            "generation_jobs", "user_briefing_deliveries", "manual_refresh_requests", "notification_jobs", "push_devices",
            "notification_settings", "subscriptions", "auth_sessions", "user_preferences", "user_favorite_teams",
            "user_followed_matches", "briefing_slots", "saved_collection_items", "saved_collections", "keyword_alerts",
            "followed_stories", "live_activity_tokens", "live_activity_starts", "user_activity_days", "premium_grants")),
        # Sales history keeps its numbers, without the person.
        "UPDATE billing_events SET user_id=NULL WHERE user_id=?",
        "DELETE FROM users WHERE id=?",
    )

    def delete_user(self, uid):
        """Erase the account and everything stored for it (App Store guideline 5.1.1(v))."""
        for statement in self.USER_DATA_DELETES: self.db.execute(statement, (uid,))
        self.db.commit()


class ApiError(Exception):
    """An expected failure with a stable error code, rendered in the API's error envelope."""
    def __init__(self, code, message, status):
        super().__init__(message); self.code=code; self.message=message; self.status=status


def not_found(message="not found"): return ApiError("RESOURCE_NOT_FOUND", message, 404)


def with_trending(latest, trending):
    """Latest news with what is trending now: matching stories get the "Em alta" flag, and trending
    stories not in the list (even outside the user's topics) join it, newest first like the rest."""
    by_article = {}
    for item in trending:
        for article_id in [item["id"], *(source.get("article_id") for source in item.get("sources", []))]:
            if article_id: by_article.setdefault(article_id, item)
    matched = set()
    for story in latest:
        hit = next((by_article[article_id] for article_id in [story["id"], *(source.get("article_id") for source in story.get("sources", []))]
                    if article_id in by_article), None)
        if hit:
            story["trending"] = hit["trending"]; matched.add(hit["id"])
    merged = [item for item in trending if item["id"] not in matched] + latest
    return sorted(merged, key=lambda item: item.get("published_at") or "", reverse=True)


class ProductService:
    """Every API use case, framework-independent: methods return payloads or raise ApiError."""
    def __init__(self, repo=None, clock=None):
        self.repo=repo or ProductRepository(); self.clock=clock
        self.config = self.repo.config
        self._on_demand_news={}
        log.info("[Backend Auth] firebase_auth_enabled=%s project_id=%s", self.config.firebase_auth_enabled, self.config.firebase_project_id or "unset")
        from .scheduling import BriefingScheduler, BriefingGenerationWorker, FixtureBriefingGenerator
        from .identity import LocalIdentityProvider, LocalAuthRateLimiter
        self.scheduler=BriefingScheduler(self.repo)
        generator=FixtureBriefingGenerator() if os.getenv("BRIEFING_GENERATOR","engine")=="fixture" else None
        self.worker=BriefingGenerationWorker(self.repo,generator=generator)
        if self.config.firebase_auth_enabled:
            from .firebase_identity import FirebaseAdminIdentityProvider
            self.identity = FirebaseAdminIdentityProvider(self.repo, self.config.firebase_project_id)
        else:
            self.identity=LocalIdentityProvider(self.repo)
        self.rate_limiter=LocalAuthRateLimiter()
        # Switches save one tap at a time: a person flipping them while testing must not hit the 10/min auth limit.
        self.settings_limiter=LocalAuthRateLimiter(limit=60)
        from .audio import AudioService
        self.audio = AudioService(self.repo)
        from .notifications import NotificationService
        self.notifications = NotificationService(self.repo)

    def local_date(self, prefs): return local_date_for(prefs, self.clock)

    # ------------------------------------------------------------- identity
    @staticmethod
    def bearer_token(authorization):
        authorization=authorization or ""
        return authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""

    def authenticate(self, authorization):
        """Resolve an Authorization header; returns ``(identity, failure_reason)``."""
        authorization=authorization or ""
        log.info("[Backend Auth] authorization_header_present=%s", bool(authorization))
        if not authorization: return None, "AUTH_MISSING_HEADER"
        if not authorization.lower().startswith("bearer "): return None, "AUTH_INVALID_SCHEME"
        token=authorization[7:].strip()
        if not token: return None, "AUTH_EMPTY_TOKEN"
        identity=self.identity.resolve(token)
        return identity, (None if identity else getattr(self.identity, "last_verify_reason", None))

    def register(self, data, client_key):
        if self.config.firebase_auth_enabled: raise ApiError("AUTH_PROVIDER_CLIENT_SIDE","use Firebase Authentication",410)
        if not self.rate_limiter.allow("register:ip:"+client_key): raise ApiError("RATE_LIMITED","too many requests",429)
        identity,token,expires=self.identity.register(data.get("email"),data.get("password"),data.get("display_name"))
        return {"user":self.repo.public_user(self.repo.get_user(identity.user_id)),"session":{"token":token,"expires_at":expires}}

    def login(self, data, client_key):
        if self.config.firebase_auth_enabled: raise ApiError("AUTH_PROVIDER_CLIENT_SIDE","use Firebase Authentication",410)
        # Per client and per account: one abusive client can no longer lock everyone out,
        # and credential stuffing against a single account is still bounded.
        login_email=str(data.get("email") or "").strip().casefold()[:254]
        if not self.rate_limiter.allow("login:ip:"+client_key) or (login_email and not self.rate_limiter.allow("login:email:"+login_email)):
            raise ApiError("RATE_LIMITED","too many requests",429)
        try: identity,token,expires=self.identity.authenticate(data)
        except PermissionError: raise ApiError("INVALID_CREDENTIALS","invalid credentials",401) from None
        return {"user":self.repo.public_user(self.repo.get_user(identity.user_id)),"session":{"token":token,"expires_at":expires}}

    def logout(self, uid, token, push_token=None):
        self.identity.revoke(token)
        # Signing out on one phone must not silence the account's other phones: with the push token,
        # only this install stops receiving. Clients that do not send it still disable every device.
        t=now_iso(); push_token=str(push_token or "").strip()
        if push_token: self.repo.db.execute("UPDATE push_devices SET enabled=0,invalidated_at=?,updated_at=? WHERE user_id=? AND push_token=?",(t,t,uid,push_token))
        else: self.repo.db.execute("UPDATE push_devices SET enabled=0,invalidated_at=?,updated_at=? WHERE user_id=?",(t,t,uid))
        self.repo.db.commit()
        return {"status":"ok"}

    def delete_account(self, uid):
        # Local data first: if the identity provider then fails, the client retries with the same
        # token, which recreates an empty user row that the retry deletes again.
        user=self.repo.get_user(uid); self.repo.delete_user(uid)
        from .avatars import delete_avatar_file
        delete_avatar_file(user)
        self.identity.delete_user((user or {}).get("firebase_uid") or uid)
        log.info("[Backend Auth] account_deleted=true")

    # ------------------------------------------------------------- public
    def client_config(self):
        return {"supported_languages":["pt-BR","en"],"supported_briefing_sizes":[5,10,15],"country_scopes":["LOCAL","GLOBAL","BOTH"],"topics":self.repo.list_topics()}

    def article_image(self, article_id):
        row=self.repo.db.execute("SELECT image_url FROM indexed_content WHERE id=?",(article_id,)).fetchone()
        if not row or not row["image_url"]: raise not_found("article image not found")
        from .article_images import ArticleImageError, load_article_image
        try: return load_article_image(row["image_url"])
        except ArticleImageError as exc:
            log.info("[IMAGE] article_id=%s result=unavailable reason=%s",article_id,str(exc))
            raise ApiError("ARTICLE_IMAGE_UNAVAILABLE","article image unavailable",502) from None

    # ------------------------------------------------------------- profile
    def preferences(self, uid):
        prefs=self.repo.get_preferences(uid)
        return {**prefs,"next_briefing":self.next_briefing(uid,prefs)} if prefs else prefs

    def save_preferences(self, uid, data):
        if isinstance(data,dict) and data.get("briefing_length")=="extended":
            from .subscriptions import require
            require(self.repo,uid,"extended_briefing")
        previous=self.repo.get_preferences(uid); saved=self.repo.save_preferences(uid,data)
        self.preferences_updated(uid,previous,saved)
        return {**saved,"next_briefing":self.next_briefing(uid,saved)}

    def next_briefing(self, uid, prefs):
        """When the next new briefing arrives: the soonest of the day's briefings not made yet, else tomorrow's first."""
        from .briefing_slots import scheduled_slots
        now=self.clock.now(prefs["timezone"]) if self.clock else datetime.now(ZoneInfo(prefs["timezone"])); today=now.date()
        made={row[0] for row in self.repo.db.execute("""SELECT slot FROM user_briefing_deliveries WHERE user_id=? AND local_date=?
            UNION ALL SELECT slot FROM generation_jobs WHERE user_id=? AND briefing_date=? AND status NOT IN ('PENDING','RETRY')""",
            (uid,today.isoformat(),uid,today.isoformat()))}
        slots=sorted(scheduled_slots(self.repo,uid,prefs),key=lambda slot:slot["time"])
        upcoming=[slot for slot in slots if slot["slot"] not in made and slot["time"]>now.strftime("%H:%M")]
        slot=upcoming[0] if upcoming else slots[0]
        day=today if upcoming else today+timedelta(days=1)
        return {"date":day.isoformat(),"time":slot["time"],"day":"TODAY" if day==today else "TOMORROW",**({"slot":slot["slot"]} if slot["slot"]!=1 else {})}

    def onboarding(self, uid):
        user=self.repo.get_user(uid)
        return {"status":user.get("onboarding_status","NOT_STARTED"),"preferences":self.repo.get_preferences(uid)}

    def complete_onboarding(self, uid, data):
        previous=self.repo.get_preferences(uid); prefs=self.repo.save_preferences(uid,data); self.repo.set_onboarding_status(uid,"COMPLETED")
        pipeline=self.preferences_updated(uid,previous,prefs,onboarding=True)
        return {"status":"COMPLETED","preferences":prefs,"generation":{"status":"SCHEDULED" if pipeline.get("scheduled") else pipeline.get("reason")}}

    def preferences_updated(self, uid, previous, current, onboarding=False):
        from .scheduling import BriefingProfile
        previous=previous or {}
        # Following everything has no topic list but is still a profile: changing its language, size or
        # coverage must also build a new briefing.
        has_profile=lambda prefs: bool(prefs.get("topics")) or prefs.get("content_scope")=="all"
        # The extended narration is part of the profile (Premium only); the plan is only read when it is involved.
        wants_extended=any(prefs.get("briefing_length")=="extended" for prefs in (previous,current))
        if wants_extended:
            from .subscriptions import has_premium_features
            wants_extended=has_premium_features(self.repo,uid)
        narration=lambda prefs: (prefs.get("briefing_length") or "standard") if wants_extended else "standard"
        old_profile=BriefingProfile.from_preferences(previous,narration(previous)).key() if has_profile(previous) else None
        new_profile=BriefingProfile.from_preferences(current,narration(current)).key() if has_profile(current) else None
        if onboarding:
            return self.scheduler.schedule_user_now(uid)
        if old_profile!=new_profile:
            return self.scheduler.regenerate_for_preferences(uid)
        if previous.get("briefing_time")!=current.get("briefing_time") or previous.get("timezone")!=current.get("timezone"):
            # Only a briefing not made yet follows the new time. One already made keeps its own time
            # (re-announcing it later would present old news as the next briefing); the new time starts tomorrow.
            self.repo.db.execute("UPDATE generation_jobs SET delivery_time=?,timezone=? WHERE user_id=? AND slot=1 AND status IN ('PENDING','RETRY')",(current["briefing_time"],current["timezone"],uid))
            self.repo.db.execute("UPDATE generation_jobs SET timezone=? WHERE user_id=? AND status IN ('PENDING','RETRY')",(current["timezone"],uid)); self.repo.db.commit()
        if previous.get("audio_voice_id")!=current.get("audio_voice_id"):
            delivery=self.repo.db.execute("SELECT id,edition_id,status FROM user_briefing_deliveries WHERE user_id=? ORDER BY local_date DESC,created_at DESC LIMIT 1",(uid,)).fetchone()
            if delivery:
                language=self.repo.db.execute("SELECT language FROM briefing_editions WHERE id=?",(delivery["edition_id"],)).fetchone()["language"]
                result=self.audio.queue_voice_for_delivery(delivery["id"],current.get("audio_voice_id"),language)
                return {"scheduled":result.get("status") in ("PENDING","GENERATING"),"audio_status":result.get("status"),"delivery_id":delivery["id"]}
            return self.scheduler.schedule_user_now(uid)
        return {"scheduled":False,"reason":"NO_PIPELINE_CHANGE"}

    def upload_avatar(self, uid, data):
        if not self.rate_limiter.allow("avatar:"+uid): raise ApiError("RATE_LIMITED","too many requests",429)
        from .avatars import save_avatar
        return {"photo_url":save_avatar(self.repo,uid,(data or {}).get("image_base64"))}

    def register_device(self, uid, data):
        if not self.rate_limiter.allow("device:"+uid): raise ApiError("RATE_LIMITED","too many requests",429)
        return self.notifications.register_device(uid,data)

    def notification_settings(self, uid, data=None):
        if not self.settings_limiter.allow("notification-settings:"+uid): raise ApiError("RATE_LIMITED","too many requests",429)
        if data is not None: self.notifications.save_settings(uid,data)
        return self.notifications.public_settings(uid)

    # ------------------------------------------------------------- articles and saved items
    def article_feedback(self, uid, story_id, rating=None, update=False):
        if update and (isinstance(rating,bool) or not isinstance(rating,int) or rating<1 or rating>5):
            raise ApiError("VALIDATION_ERROR","rating must be an integer between 1 and 5",400)
        return self.repo.article_feedback(uid,story_id,rating if update else None)

    def saved_page(self, uid, limit, cursor, topic):
        limit=max(1,min(int(limit),100)); offset=max(0,int(cursor or 0))
        items,has_more=self.repo.saved_stories(uid,limit=limit,offset=offset,topic_id=topic)
        return {"items":items,"next_cursor":str(offset+limit) if has_more else None}

    def saved_progress(self, uid, story_id, raw_progress):
        try: progress=float(raw_progress)
        except (TypeError,ValueError): raise ApiError("VALIDATION_ERROR","progress must be a number",400) from None
        if progress<0 or progress>100: raise ApiError("VALIDATION_ERROR","progress must be between 0 and 100",400)
        if not self.repo.saved_story_progress(uid,story_id,progress): raise not_found("saved story not found")
        return {"status":"saved","progress":progress}

    def save_story(self, uid, data):
        try: return {"item":self.repo.save_story(uid,data.get("story",data))}
        except (TypeError,ValueError) as exc: raise ApiError("VALIDATION_ERROR",str(exc),400) from None

    def save_briefing(self, uid, briefing_id):
        if not isinstance(briefing_id,str) or not briefing_id: raise ApiError("VALIDATION_ERROR","briefing_id is required",400)
        if not self.repo.save_briefing(uid,briefing_id): raise not_found("briefing not found")
        return {"status":"saved"}

    # ------------------------------------------------------------- briefings
    def client_briefing(self, uid, local_date=None):
        local_date=local_date or self.local_date(self.repo.get_preferences(uid))
        delivery=self.repo.db.execute("SELECT * FROM user_briefing_deliveries WHERE user_id=? AND local_date=? ORDER BY CASE WHEN status='READY' THEN 0 ELSE 1 END,created_at DESC LIMIT 1",(uid,local_date)).fetchone()
        if delivery:
            from .scheduling import serialize_edition, BriefingProfile
            edition=serialize_edition(self.repo,delivery["edition_id"]); items=[]
            for item in (edition or {}).get("items",[]): items.append({k:item.get(k) for k in ("id","position","headline","summary","why_it_matters","key_points","confidence","evidence_quality","sources","warnings","summary_provider","primary_taxonomy_id","primary_taxonomy_label","image_url")})
            from .briefing_slots import slot_for
            prefs=self.repo.get_preferences(uid)
            current_key=BriefingProfile.for_slot(prefs,slot_for(self.repo,uid,delivery["slot"] or 1,prefs) or {}).key()
            status=delivery["status"]; audio_status=delivery["audio_status"]; audio_metadata=None
            if status=="READY":
                if not delivery["audio_artifact_id"]: status="CONTENT_READY"; audio_status="PENDING"
                else:
                    audio_metadata=self.audio.audio_for_artifact(delivery["audio_artifact_id"])
                    if audio_metadata.get("status")!="READY": status="FAILED"; audio_status="FAILED"
            audio_url=None
            if audio_metadata and audio_metadata.get("status")=="READY":
                audio_url=("/api/v1/me/briefings/"+delivery["id"]+"/audio/file?v="+audio_metadata["asset_version"]+"&voice="+audio_metadata["voice"])
            return {"id":delivery["id"],"delivery_id":delivery["id"],"edition_id":delivery["edition_id"],"date":local_date,"status":status,"content_status":(edition or {}).get("status"),"audio_status":audio_status,"selected_voice_id":delivery["selected_voice_id"],"active_voice_id":delivery["active_voice_id"],"voice_fallback_reason":delivery["voice_fallback_reason"],"audio_variant_id":delivery["audio_artifact_id"],"active_audio_variant_id":delivery["audio_artifact_id"],"audio_url":audio_url,"audio_duration_ms":audio_metadata.get("duration_ms") if audio_url else None,"script_id":delivery["script_id"],"generation_stage":delivery["generation_stage"],"generation_started_at":delivery["generation_started_at"],"generation_updated_at":delivery["generation_updated_at"],"generation_error_code":delivery["generation_error_code"],"generated_at":(edition or {}).get("generated_at"),"items":items,"profile_stale":bool(edition and edition["profile_key"]!=current_key and not edition["profile_key"].startswith((current_key+"_manual_",current_key+"_user_"))),"fallback_levels":sorted({w for item in items for w in item.get("warnings",[]) if isinstance(w,str) and w.startswith("FALLBACK_")}),**self._slot_fields(delivery,edition)}
        job=self.repo.db.execute("SELECT status,error_code FROM generation_jobs WHERE user_id=? AND briefing_date=? AND slot=1",(uid,local_date)).fetchone()
        return {"date":local_date,"status":"FAILED" if job and job["status"]=="FAILED" else "PENDING","generated_at":None,"items":[],"error_code":job["error_code"] if job and job["status"]=="FAILED" else None}

    @staticmethod
    def _slot_fields(delivery, edition):
        """Which of the day's briefings a delivery is: its slot, kind (SCHEDULED, EXTRA, ON_DEMAND), theme and time."""
        theme=delivery["theme"]
        label=taxonomy().nodes.get(theme,{}).get("name") if theme else None
        return {"slot":delivery["slot"] or 1,"kind":delivery["kind"] or "SCHEDULED","theme":theme,"theme_label":label,
                "delivery_time":delivery["delivery_time"],"narration":(edition or {}).get("narration") or "standard"}

    def _history_cutoff(self, uid):
        """The first local date a Básico account still sees in its history (None: all of it)."""
        from .subscriptions import limit
        days=limit(self.repo,uid,"history_days")
        if days is None: return None
        prefs=self.repo.get_preferences(uid)
        return (datetime.fromisoformat(self.local_date(prefs))-timedelta(days=days-1)).date().isoformat()

    def client_history(self, uid, limit=20, offset=0, include_audio=False):
        from .scheduling import serialize_edition
        cutoff=self._history_cutoff(uid)
        deliveries=list(self.repo.db.execute("SELECT * FROM user_briefing_deliveries WHERE user_id=? AND local_date>=? ORDER BY local_date DESC,created_at DESC LIMIT ? OFFSET ?",(uid,cutoff or "",limit+1,offset)))
        progress_by_delivery={row["delivery_id"]:row for row in self.repo.db.execute(
            "SELECT delivery_id,progress_seconds,duration_seconds,completed_at FROM briefing_listening_progress WHERE user_id=?",(uid,))}
        result=[]
        for delivery in deliveries[:limit]:
            edition=serialize_edition(self.repo,delivery["edition_id"])
            row={"id":delivery["id"],"delivery_id":delivery["id"],"edition_id":delivery["edition_id"],"date":delivery["local_date"],"status":delivery["status"],"audio_status":delivery["audio_status"],"selected_voice_id":delivery["selected_voice_id"],"active_voice_id":delivery["active_voice_id"],"audio_variant_id":delivery["audio_artifact_id"],"script_id":delivery["script_id"],"generation_stage":delivery["generation_stage"],"generation_started_at":delivery["generation_started_at"],"generation_updated_at":delivery["generation_updated_at"],"generation_error_code":delivery["generation_error_code"],"generated_at":(edition or {}).get("generated_at"),"items":[{k:item.get(k) for k in ("id","position","headline","summary","why_it_matters","key_points","confidence","evidence_quality","sources","primary_taxonomy_id","primary_taxonomy_label","image_url")} for item in (edition or {}).get("items",[])],**self._slot_fields(delivery,edition)}
            progress=progress_by_delivery.get(delivery["id"])
            if progress:
                row.update(listening_progress_seconds=progress["progress_seconds"],listening_duration_seconds=progress["duration_seconds"],completed_at=progress["completed_at"])
            metadata=self.audio.audio_for_artifact(delivery["audio_artifact_id"]) if delivery["audio_artifact_id"] else {"status":"NOT_AVAILABLE"}
            if delivery["status"]=="READY" and delivery["audio_artifact_id"]:
                if metadata.get("status")!="READY": row.update(status="FAILED",audio_status="FAILED",generation_error_code=metadata.get("error_code"))
                else: row["audio_duration_ms"]=metadata.get("duration_ms")
            elif delivery["status"]=="READY":
                row.update(status="CONTENT_READY",audio_status="PENDING")
            if include_audio and edition and self.config.audio_enabled:
                row["audio_duration_ms"]=metadata.get("duration_ms") if metadata.get("status")=="READY" else None
            result.append(row)
        return result, (str(offset+limit) if len(deliveries)>limit else None)

    def history_page(self, uid, limit, cursor):
        limit=max(1,min(int(limit),50)); offset=int(cursor or 0)
        page,next_cursor=self.client_history(uid,limit,offset,include_audio=True)
        out={"items":page,"next_cursor":next_cursor}
        cutoff=self._history_cutoff(uid)
        if cutoff and not next_cursor:
            # The end of a Básico history: say when older briefings exist (the app offers Premium there).
            older=self.repo.db.execute("SELECT COUNT(*) FROM user_briefing_deliveries WHERE user_id=? AND local_date<?",(uid,cutoff)).fetchone()[0]
            out["limited"]={"days":(datetime.fromisoformat(self.local_date(self.repo.get_preferences(uid)))-datetime.fromisoformat(cutoff)).days+1,"older_count":older}
        return out

    def search_briefings(self, uid, query, limit=30):
        """Premium: stories of the person's past briefings whose headline or summary has every word of ``query``."""
        from .subscriptions import require
        require(self.repo,uid,"briefing_search")
        from .scheduling import serialize_edition
        import unicodedata
        fold=lambda value:"".join(ch for ch in unicodedata.normalize("NFD",(value or "").casefold()) if unicodedata.category(ch)!="Mn")
        words=[word for word in fold(query).split() if len(word)>1]
        if not words: raise ApiError("VALIDATION_ERROR","type at least one word to search",400)
        results=[]; seen=set()
        for delivery in self.repo.db.execute("SELECT * FROM user_briefing_deliveries WHERE user_id=? ORDER BY local_date DESC,created_at DESC LIMIT 400",(uid,)).fetchall():
            edition=serialize_edition(self.repo,delivery["edition_id"])
            for item in (edition or {}).get("items",[]):
                text=fold(" ".join(str(item.get(key) or "") for key in ("headline","summary")))
                key=item.get("event_id") or item.get("headline")
                if key in seen or not all(word in text for word in words): continue
                seen.add(key)
                results.append({"briefing_id":delivery["id"],"date":delivery["local_date"],**self._slot_fields(delivery,edition),
                    "item":{k:item.get(k) for k in ("id","position","headline","summary","sources","primary_taxonomy_id","primary_taxonomy_label","image_url")}})
                if len(results)>=limit: return {"items":results}
        return {"items":results}

    def trending(self, uid, limit=5):
        from .trending import trending_stories
        return trending_stories(self.repo, uid, limit)

    def client_home(self, uid):
        preferences=self.preferences(uid) or {}
        today=self.client_briefing(uid,self.local_date(preferences))
        history,_=self.client_history(uid,50)
        latest=next((item for item in history if item.get("status")=="READY" and item.get("items")),None)
        # A scheduled delivery's visual edition is the current briefing as soon
        # as it exists. Never pair an older READY audio with newer visual items.
        if today.get("items"):
            latest=today
        trending=self.trending(uid)
        return {"preferences":preferences,"today_briefing":today,"latest_briefing":latest,
            "topics":self.repo.list_topics(),"latest_news":with_trending(self.repo.latest_news(uid,12),trending),
            "trending":trending,
            "saved_story_ids":[row["story_id"] for row in self.repo.db.execute("SELECT story_id FROM saved_stories WHERE user_id=?",(uid,))]}

    def briefing(self, uid, briefing_id):
        briefing=self.repo.briefing_for_user(uid,briefing_id)
        if not briefing: raise not_found("briefing not found")
        return briefing

    def listening_progress(self, uid, delivery_id, data):
        delivery=self.repo.db.execute("SELECT id FROM user_briefing_deliveries WHERE id=? AND user_id=?",(delivery_id,uid)).fetchone()
        if not delivery: raise not_found("briefing not found")
        try: position=float(data.get("progress_seconds")); duration=float(data.get("duration_seconds"))
        except (TypeError,ValueError): raise ApiError("VALIDATION_ERROR","progress and duration must be numbers",400) from None
        if position<0 or duration<=0 or position>duration+1: raise ApiError("VALIDATION_ERROR","invalid listening progress",400)
        position=min(position,duration); completed=position>=duration*.95; updated=now_iso()
        self.repo.db.execute("""INSERT INTO briefing_listening_progress(delivery_id,user_id,progress_seconds,duration_seconds,completed_at,updated_at)
            VALUES(?,?,?,?,?,?) ON CONFLICT(delivery_id,user_id) DO UPDATE SET progress_seconds=excluded.progress_seconds,
            duration_seconds=excluded.duration_seconds,completed_at=COALESCE(briefing_listening_progress.completed_at,excluded.completed_at),updated_at=excluded.updated_at""",
            (delivery["id"],uid,position,duration,updated if completed else None,updated)); self.repo.db.commit()
        return {"status":"saved","completed":completed}

    def request_refresh(self, uid):
        """Queue a manual regeneration (internal/admin compatibility; the app relies on scheduled deliveries)."""
        prefs=self.repo.get_preferences(uid)
        if not prefs or (prefs.get("content_scope", "selected") != "all" and not prefs.get("topics")):
            raise ApiError("PREFERENCES_INCOMPLETE","configure topics before refreshing",409)
        active=self.repo.db.execute("SELECT id,status,stage FROM manual_refresh_requests WHERE user_id=? AND status IN ('PENDING','GENERATING') ORDER BY requested_at DESC LIMIT 1",(uid,)).fetchone()
        if active: return {"generation_id":active["id"],"reason":"MANUAL_REFRESH","status":active["status"],"stage":active["stage"],"coalesced":True}
        generation_id="generation_"+uuid.uuid4().hex; requested=now_iso()
        self.repo.db.execute("INSERT INTO manual_refresh_requests(id,user_id,reason,status,stage,requested_at,updated_at,selected_voice_id) VALUES(?,?,?,'PENDING','QUEUED',?,?,?)",(generation_id,uid,"MANUAL_REFRESH",requested,requested,prefs.get("audio_voice_id")))
        self.repo.db.commit()
        return {"generation_id":generation_id,"reason":"MANUAL_REFRESH","status":"PENDING","stage":"QUEUED","coalesced":False}

    def request_on_demand(self, uid):
        """Premium "Gerar agora": a new briefing right away with what is new since the day's earlier ones."""
        from .subscriptions import limit, require
        from .briefing_slots import ON_DEMAND_FIRST_SLOT
        require(self.repo,uid,"on_demand_briefing")
        prefs=self.repo.get_preferences(uid)
        if not prefs or (prefs.get("content_scope", "selected") != "all" and not prefs.get("topics")):
            raise ApiError("PREFERENCES_INCOMPLETE","configure topics before generating",409)
        active=self._active_on_demand(uid)
        if active: return {"generation_id":active["id"],"reason":"ON_DEMAND","status":active["status"],"stage":active["stage"],"coalesced":True}
        # Known to have nothing new since the earlier briefings: finished at once as NO_ELIGIBLE_CONTENT, without a
        # queue, an audio or a use of the day, which every app version shows as "nada novo". The count itself is
        # never made here: on a busy server it takes longer than the app waits (10 s), so when it is not known the
        # request is queued and the worker, composing with only_new, ends it the same way if nothing is new.
        if self._cached_on_demand_count(uid,prefs)==0:
            generation_id="generation_"+uuid.uuid4().hex; stamp=now_iso()
            self.repo.db.execute("""INSERT INTO manual_refresh_requests(id,user_id,reason,status,stage,requested_at,updated_at,finished_at,error_code,error_message)
                VALUES(?,?,'ON_DEMAND','FAILED','FAILED_FINAL',?,?,?,'NO_ELIGIBLE_CONTENT','nothing new since your last briefing')""",(generation_id,uid,stamp,stamp,stamp))
            self.repo.db.commit()
            return {"generation_id":generation_id,"reason":"ON_DEMAND","status":"FAILED","stage":"FAILED_FINAL","error_code":"NO_ELIGIBLE_CONTENT","coalesced":False}
        local_date=self.local_date(prefs)
        start=datetime.combine(datetime.fromisoformat(local_date).date(),datetime.min.time(),ZoneInfo(prefs["timezone"])).astimezone(timezone.utc)
        # Under the write lock, so two taps that arrive together make one briefing.
        self.repo.db.begin_immediate()
        try:
            active=self._active_on_demand(uid)
            if active:
                self.repo.db.rollback()
                return {"generation_id":active["id"],"reason":"ON_DEMAND","status":active["status"],"stage":active["stage"],"coalesced":True}
            used=self.repo.db.execute("SELECT COUNT(*) FROM manual_refresh_requests WHERE user_id=? AND reason='ON_DEMAND' AND status<>'FAILED' AND requested_at>=?",(uid,iso(start))).fetchone()[0]
            allowed=limit(self.repo,uid,"on_demand_per_day")
            if used>=allowed: raise ApiError("ON_DEMAND_LIMIT",f"you can make {allowed} briefing(s) on request a day",429)
            taken=[row[0] for row in self.repo.db.execute("SELECT slot FROM user_briefing_deliveries WHERE user_id=? AND local_date=? AND slot>=? UNION SELECT slot FROM manual_refresh_requests WHERE user_id=? AND slot IS NOT NULL AND requested_at>=?",(uid,local_date,ON_DEMAND_FIRST_SLOT,uid,iso(start)))]
            slot=max([ON_DEMAND_FIRST_SLOT-1,*taken])+1
            generation_id="generation_"+uuid.uuid4().hex; requested=now_iso()
            self.repo.db.execute("INSERT INTO manual_refresh_requests(id,user_id,reason,status,stage,requested_at,updated_at,selected_voice_id,slot) VALUES(?,?,'ON_DEMAND','PENDING','QUEUED',?,?,?,?)",(generation_id,uid,requested,requested,prefs.get("audio_voice_id"),slot))
            self.repo.db.commit()
        except Exception:
            self.repo.db.rollback(); raise
        return {"generation_id":generation_id,"reason":"ON_DEMAND","status":"PENDING","stage":"QUEUED","coalesced":False,"remaining_today":allowed-used-1}

    def _active_on_demand(self, uid):
        return self.repo.db.execute("SELECT id,status,stage FROM manual_refresh_requests WHERE user_id=? AND reason='ON_DEMAND' AND status IN ('PENDING','GENERATING') ORDER BY requested_at DESC LIMIT 1",(uid,)).fetchone()

    ON_DEMAND_NEWS_SECONDS=600

    def on_demand_news(self, uid):
        """Premium "Gerar agora": how many stories are new since the person's earlier briefings.

        The very selection the briefing would be made with, without making it. Kept until news are
        collected, a briefing arrives or the preferences change, and ten minutes at most.
        ``generation_id``: a briefing on request already being made, which the app follows.
        """
        from .subscriptions import require
        require(self.repo,uid,"on_demand_briefing")
        active=self._active_on_demand(uid)
        if active: return {"new_count":0,"generating":True,"generation_id":active["id"]}
        prefs=self.repo.get_preferences(uid)
        if not prefs or (prefs.get("content_scope", "selected") != "all" and not prefs.get("topics")):
            return {"new_count":0,"generating":False,"generation_id":None}
        cached=self._cached_on_demand_count(uid,prefs)
        if cached is not None:
            return {"new_count":cached,"generating":False,"generation_id":None}
        key=self._on_demand_key(uid,prefs)
        from .briefing_slots import ON_DEMAND_FIRST_SLOT, slot_for
        from .content import compose
        from .scheduling import BriefingProfile
        profile=BriefingProfile.for_slot(prefs,slot_for(self.repo,uid,ON_DEMAND_FIRST_SLOT,prefs))
        # The same call the worker makes for "Gerar agora" (scheduling._run_manual_refresh).
        payload=compose(self.repo,profile.topics,profile.language,profile.briefing_size,profile.country_scope,briefing_date=self.local_date(prefs),user_id=uid,tz=prefs["timezone"],since_today=True,only_new=True)
        count=len(payload.get("items") or [])
        self._on_demand_news[uid]=(key,time.monotonic(),count)
        return {"new_count":count,"generating":False,"generation_id":None}

    def _on_demand_key(self, uid, prefs):
        """What the count of new stories depends on: the day, the preferences, the last collection and briefings."""
        db=self.repo.db
        return (self.local_date(prefs),json.dumps(prefs,sort_keys=True,default=str),
                db.execute("SELECT MAX(completed_at) FROM content_ingestion_runs").fetchone()[0],
                db.execute("SELECT MAX(generated_at) FROM briefing_editions WHERE user_id=?",(uid,)).fetchone()[0],
                db.execute("SELECT MAX(created_at) FROM user_briefing_deliveries WHERE user_id=?",(uid,)).fetchone()[0])

    def _cached_on_demand_count(self, uid, prefs):
        """The count of new stories if it is known and still valid, else None (cheap: never composes)."""
        cached=self._on_demand_news.get(uid)
        if cached and cached[0]==self._on_demand_key(uid,prefs) and time.monotonic()-cached[1]<self.ON_DEMAND_NEWS_SECONDS:
            return cached[2]
        return None

    def generation_status(self, uid, generation_id):
        row=self.repo.db.execute("SELECT * FROM manual_refresh_requests WHERE id=? AND user_id=?",(generation_id,uid)).fetchone()
        if not row: raise not_found("generation not found")
        audio_status=None
        if row["edition_id"]:
            metadata=self.audio.audio_for_edition(row["edition_id"],voice=row["selected_voice_id"])
            audio_status=metadata.get("status")
        ingestion=self.repo.db.execute("SELECT * FROM content_ingestion_runs WHERE id=?",(row["ingestion_run_id"],)).fetchone() if row["ingestion_run_id"] else None
        ingestion_summary={"run_id":ingestion["id"],"status":ingestion["status"],"started_at":ingestion["started_at"],"completed_at":ingestion["completed_at"],"sources_attempted":ingestion["sources_attempted"],"sources_successful":ingestion["sources_successful"],"articles_seen":ingestion["articles_seen"],"articles_new":ingestion["articles_new"],"articles_updated":ingestion["articles_updated"],"articles_unchanged":ingestion["articles_unchanged"],"source_errors":len(json.loads(ingestion["errors_json"] or "{}"))} if ingestion else None
        safe_message=("A atualização falhou durante a etapa de áudio." if audio_status=="FAILED" else "A atualização não foi concluída. Tente novamente mais tarde.") if row["status"]=="FAILED" else None
        return {"generation_id":row["id"],"reason":row["reason"],"status":row["status"],"stage":row["stage"],"requested_at":row["requested_at"],"started_at":row["started_at"],"updated_at":row["updated_at"],"ingestion_run_id":row["ingestion_run_id"],"ingestion":ingestion_summary,"edition_id":row["edition_id"],"content_ready":bool(row["edition_id"]),"audio_status":audio_status,"audio_job_id":row["audio_job_id"],"selected_voice_id":row["selected_voice_id"],"audio_variant_id":row["audio_variant_id"],"error_code":row["error_code"],"error_message_safe":safe_message,"ready_at":row["finished_at"] if row["status"]=="READY" else None,"delivery_id":self._generation_delivery(row)}

    def _generation_delivery(self, row):
        """The briefing a finished generation made (the app opens it)."""
        if row["status"]!="READY" or not row["edition_id"]: return None
        found=self.repo.db.execute("SELECT id FROM user_briefing_deliveries WHERE user_id=? AND edition_id=? ORDER BY created_at DESC LIMIT 1",(row["user_id"],row["edition_id"])).fetchone()
        return found["id"] if found else None

    def retry_generation_audio(self, uid, generation_id):
        row=self.repo.db.execute("SELECT * FROM manual_refresh_requests WHERE id=? AND user_id=?",(generation_id,uid)).fetchone()
        if not row or not row["edition_id"]: raise not_found("generation audio not found")
        if row["status"]!="FAILED": raise ApiError("GENERATION_NOT_FAILED","audio retry is only available after a failed generation",409)
        edition=self.repo.db.execute("SELECT language FROM briefing_editions WHERE id=? AND status='READY'",(row["edition_id"],)).fetchone()
        if not edition: raise ApiError("EDITION_NOT_READY","edition is not ready",409)
        result=self.audio.retry(row["edition_id"],edition["language"],row["selected_voice_id"])
        job=self.repo.db.execute("SELECT id FROM audio_generation_jobs WHERE edition_id=? AND voice=? ORDER BY created_at DESC LIMIT 1",(row["edition_id"],row["selected_voice_id"])).fetchone()
        self.repo.db.execute("UPDATE manual_refresh_requests SET status='GENERATING',stage='AUDIO_QUEUED',audio_job_id=?,audio_variant_id=NULL,error_code=NULL,error_message=NULL,finished_at=NULL,updated_at=? WHERE id=?",(job["id"] if job else None,now_iso(),row["id"])); self.repo.db.commit()
        return {"generation_id":row["id"],"status":"GENERATING","stage":"AUDIO_QUEUED","audio_status":result.get("status"),"audio_job_id":job["id"] if job else None}

    # ------------------------------------------------------------- audio
    def _delivery(self, uid, delivery_id):
        return self.repo.db.execute("SELECT * FROM user_briefing_deliveries WHERE id=? AND user_id=?",(delivery_id,uid)).fetchone()

    def _edition_language(self, edition_id):
        return self.repo.db.execute("SELECT language FROM briefing_editions WHERE id=?",(edition_id,)).fetchone()["language"]

    def briefing_audio(self, uid, delivery_id):
        delivery=self._delivery(uid,delivery_id)
        if not delivery: raise not_found("briefing not found")
        edition_id=delivery["edition_id"]; language=self._edition_language(edition_id)
        preferred=delivery["selected_voice_id"] or self.repo.get_preferences(uid).get("audio_voice_id")
        requested=self.audio.effective_voice(preferred,language)
        active=delivery["active_voice_id"]
        voice=active or requested
        if self.config.audio_enabled and voice:
            result=self.audio.audio_for_artifact(delivery["audio_artifact_id"]) if delivery["audio_artifact_id"] else {"status":delivery["audio_status"] or "NOT_AVAILABLE"}
            if delivery["audio_artifact_id"] and result.get("status")!="READY":
                queued=self.audio.audio_for_edition(edition_id,language,voice)
                if queued.get("status") in {"PENDING","GENERATING","VALIDATING"}: result=queued
        else: result={"status":"NOT_AVAILABLE"}
        result["selected_voice_id"]=preferred; result["active_voice_id"]=active; result["voice_fallback_reason"]=delivery["voice_fallback_reason"]
        result["active_audio_variant_id"]=delivery["audio_artifact_id"]
        result["audio_duration_ms"]=result.get("duration_ms")
        result["audio_status"]=delivery["audio_status"]
        result["generation_stage"]=delivery["generation_stage"]
        result["generation_started_at"]=delivery["generation_started_at"]
        result["generation_updated_at"]=delivery["generation_updated_at"]
        result["generation_error_code"]=delivery["generation_error_code"]
        if result.get("status")=="READY" and delivery["audio_artifact_id"] and result.get("artifact_id")!=delivery["audio_artifact_id"]:
            result={**result,"status":"NOT_AVAILABLE","error_code":"DELIVERY_AUDIO_MISMATCH"}
        if result.get("status")=="READY": result["audio_url"]="/api/v1/me/briefings/"+delivery_id+"/audio/file?v="+result["asset_version"]+"&voice="+voice
        return result

    def retry_briefing_audio(self, uid, delivery_id):
        delivery=self._delivery(uid,delivery_id)
        if not delivery: raise not_found("briefing not found")
        edition=self.repo.db.execute("SELECT language,status FROM briefing_editions WHERE id=?",(delivery["edition_id"],)).fetchone()
        if not edition or edition["status"]!="READY": raise ApiError("EDITION_NOT_READY","edition is not ready",409)
        voice=delivery["selected_voice_id"] or (self.repo.get_preferences(uid) or {}).get("audio_voice_id")
        from .audio import PermanentAudioError
        try: result=self.audio.retry(delivery["edition_id"],edition["language"],voice)
        except PermanentAudioError as exc: raise ApiError(exc.code,str(exc),409) from None
        return {"delivery_id":delivery["id"],"edition_id":delivery["edition_id"],"status":result.get("status"),"audio_status":result.get("status"),"stage":"AUDIO_QUEUED","selected_voice_id":voice}

    def briefing_audio_file(self, uid, delivery_id, requested_voice=None, requested_version=None):
        """Resolve the playable file; returns ``(path, mime_type)``."""
        delivery=self._delivery(uid,delivery_id)
        edition_id=delivery["edition_id"] if delivery else None; prefs=self.repo.get_preferences(uid)
        language=self._edition_language(edition_id) if edition_id else prefs["language"]
        available={voice["id"] for voice in self.audio.available_voices(language)}
        available.add(self.audio.default_voice(language))
        if requested_voice and requested_voice not in available: raise not_found("audio not available")
        voice=requested_voice or self.audio.effective_voice(prefs.get("audio_voice_id"),language)
        if delivery and delivery["audio_artifact_id"] and self.config.audio_enabled: result=self.audio.audio_for_artifact(delivery["audio_artifact_id"])
        elif edition_id and self.config.audio_enabled and voice: result=self.audio.audio_for_edition(edition_id,voice=voice)
        else: result={"status":"NOT_AVAILABLE"}
        if result.get("status")!="READY": raise not_found("audio not ready")
        if delivery and delivery["audio_artifact_id"] and (delivery["active_voice_id"]!=result.get("voice") or requested_voice!=delivery["active_voice_id"] or requested_version!=result.get("asset_version")):
            raise not_found("audio variant is no longer active")
        if result.get("mime_type") not in {"audio/wav", "audio/mpeg", "audio/mp4", "audio/aac"}: raise not_found("audio not available")
        if delivery and delivery["audio_artifact_id"]:
            audio_path=self.audio.storage.resolve(self.repo.db.execute("SELECT storage_path FROM audio_artifacts WHERE id=?",(delivery["audio_artifact_id"],)).fetchone()["storage_path"])
        else:
            audio_path=self.audio.artifact_path(edition_id,voice=voice)
        if not audio_path: raise not_found("audio not available")
        return audio_path, result["mime_type"]

    def voice_language(self, uid, requested=None):
        """Onboarding lists voices for the language just picked, before it is saved; otherwise the saved one."""
        if requested in {"pt-BR", "en"}: return requested
        return (self.repo.get_preferences(uid) or {}).get("language") or self.config.default_language

    def voice_catalog(self, uid, language=None):
        return self.audio.voice_catalog(self.voice_language(uid,language))

    def voice_preview(self, uid, voice_id, language=None):
        language=self.voice_language(uid,language)
        if voice_id not in {voice["id"] for voice in self.audio.available_voices(language)}: raise not_found("voice not available")
        try: preview=self.audio.voice_preview(voice_id,language)
        except Exception: raise ApiError("VOICE_PREVIEW_UNAVAILABLE","voice preview unavailable",503) from None
        return preview, ("audio/mpeg" if preview.suffix==".mp3" else "audio/wav")

    # ------------------------------------------------------------- development
    def pipeline_diagnostic(self, uid):
        delivery=self.repo.db.execute("SELECT * FROM user_briefing_deliveries WHERE user_id=? ORDER BY local_date DESC,created_at DESC LIMIT 1",(uid,)).fetchone()
        if not delivery: return {"delivery":None}
        job=self.repo.db.execute("SELECT id,status,attempt_count,max_attempts,scheduled_for,started_at,finished_at,error_code,error_message,profile_key FROM generation_jobs WHERE user_id=? AND briefing_date=? AND slot=?",(uid,delivery["local_date"],delivery["slot"] or 1)).fetchone()
        audio_job=self.repo.db.execute("SELECT id,status,stage,voice,script_version,attempt_count,max_attempts,created_at,started_at,updated_at,finished_at,error_code,error_message FROM audio_generation_jobs WHERE edition_id=? AND voice=? ORDER BY created_at DESC LIMIT 1",(delivery["edition_id"],delivery["selected_voice_id"] or delivery["active_voice_id"] or "")).fetchone()
        artifact=self.repo.db.execute("SELECT id,status,provider,voice,language,mime_type,storage_path,duration_ms,size_bytes,checksum,created_at FROM audio_artifacts WHERE id=?",(delivery["audio_artifact_id"],)).fetchone() if delivery["audio_artifact_id"] else None
        phases=list(self.repo.db.execute("SELECT phase,duration_ms,recorded_at FROM generation_job_phases WHERE job_id=? ORDER BY id",(job["id"],))) if job else []
        audio_phases=list(self.repo.db.execute("SELECT phase,duration_ms,started_at,finished_at,status,error_code FROM audio_job_phases WHERE audio_job_id=? ORDER BY id",(audio_job["id"],))) if audio_job else []
        return {"delivery":{"id":delivery["id"],"edition_id":delivery["edition_id"],"date":delivery["local_date"],"status":delivery["status"],"audio_status":delivery["audio_status"],"stage":delivery["generation_stage"],"selected_voice_id":delivery["selected_voice_id"],"active_voice_id":delivery["active_voice_id"],"script_id":delivery["script_id"],"audio_artifact_id":delivery["audio_artifact_id"],"started_at":delivery["generation_started_at"],"updated_at":delivery["generation_updated_at"],"error_code":delivery["generation_error_code"],"error_message":delivery["generation_error_message"]},"generation_job":dict(job) if job else None,"audio_job":dict(audio_job) if audio_job else None,"audio_artifact":dict(artifact) if artifact else None,"generation_phases":[dict(x) for x in phases],"audio_phases":[dict(x) for x in audio_phases]}

    def briefing_diagnostic(self, uid):
        from .content import candidate_counts
        from .scheduling import BriefingProfile
        raw=self.repo.db.execute("SELECT topics_json FROM user_preferences WHERE user_id=?",(uid,)).fetchone()
        canonical,unknown=taxonomy().canonicalize(json.loads(raw["topics_json"]) if raw else [])
        prefs=self.repo.get_preferences(uid)
        profile=BriefingProfile.from_preferences(prefs); local_date=self.local_date(prefs)
        job=self.repo.db.execute("SELECT status,error_code,error_message FROM generation_jobs WHERE user_id=? AND briefing_date=? AND slot=1",(uid,local_date)).fetchone()
        edition=self.repo.db.execute("SELECT e.status,e.item_count FROM briefing_editions e JOIN user_briefing_deliveries d ON d.edition_id=e.id WHERE d.user_id=? AND d.local_date=? AND d.slot=1",(uid,local_date)).fetchone()
        fallback=[]; diagnostic_items=[]
        for item in self.repo.db.execute("""SELECT i.event_id,i.sources_json,i.warnings_json,i.primary_taxonomy_id,
            i.primary_taxonomy_label,i.primary_taxonomy_reason,i.matched_taxonomy_ids_json,i.user_interest_matches_json
            FROM briefing_edition_items i JOIN user_briefing_deliveries d ON d.edition_id=i.edition_id
            WHERE d.user_id=? AND d.local_date=? AND d.slot=1 ORDER BY i.position""",(uid,local_date)):
            fallback.extend(w for w in json.loads(item["warnings_json"]) if isinstance(w,str) and w.startswith("FALLBACK_"))
            sources=json.loads(item["sources_json"])
            first=sources[0] if sources else None
            diagnostic_items.append({"content_id":first.get("article_id") if isinstance(first,dict) else item["event_id"],
                "matched_taxonomy_ids":json.loads(item["matched_taxonomy_ids_json"] or "[]"),
                "user_interest_matches":json.loads(item["user_interest_matches_json"] or "[]"),
                "primary_taxonomy_id":item["primary_taxonomy_id"],"primary_taxonomy_label":item["primary_taxonomy_label"],
                "primary_taxonomy_reason":item["primary_taxonomy_reason"]})
        return {"effective_canonical_taxonomy_ids":canonical,"unknown_taxonomy_ids":unknown,"profile_key":profile.key(),**candidate_counts(self.repo,canonical),"edition_status":edition["status"] if edition else None,"job_status":job["status"] if job else None,"last_error":job["error_code"] if job else None,"fallback_levels":sorted(set(fallback)),"items":diagnostic_items,"pipeline":self.pipeline_diagnostic(uid)}

    def dev_jobs(self):
        return {"items":[dict(x) for x in self.repo.db.execute("SELECT * FROM generation_jobs ORDER BY created_at DESC")],"count":self.repo.db.execute("SELECT COUNT(*) FROM generation_jobs").fetchone()[0]}

    def dev_generate_audio(self, identifier):
        edition_id=identifier
        if not self.repo.db.execute("SELECT id FROM briefing_editions WHERE id=?",(edition_id,)).fetchone():
            delivery=self.repo.db.execute("SELECT edition_id FROM user_briefing_deliveries WHERE id=?",(edition_id,)).fetchone(); edition_id=delivery["edition_id"] if delivery else None
        if not edition_id: raise not_found("briefing not found")
        return self.audio.request(edition_id)


def seed_dev(path=None): return ProductRepository(path).create_dev_user()
