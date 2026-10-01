import json, sqlite3, time
from pathlib import Path
from .models import Article, NewsEvent, iso, article_from_row
from .images import canonical_image_url
from .paths import ENGINE_DATA

class Store:
    def __init__(self, path=None):
        path = path or (ENGINE_DATA / "news_engine.sqlite3")
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path); self.db.row_factory = sqlite3.Row
        self.db.executescript("""CREATE TABLE IF NOT EXISTS articles (article_id TEXT PRIMARY KEY, source_id TEXT, source_name TEXT, title TEXT, description TEXT, url TEXT, canonical_url TEXT, published_at TEXT, collected_at TEXT, language TEXT, categories TEXT, author TEXT, image_url TEXT, image_source TEXT, image_checked_at TEXT); CREATE TABLE IF NOT EXISTS runs (run_id INTEGER PRIMARY KEY AUTOINCREMENT, generated_at TEXT, stats_json TEXT); CREATE TABLE IF NOT EXISTS source_health (source_id TEXT PRIMARY KEY,last_status TEXT,last_success_at TEXT,last_failure_at TEXT,consecutive_failures INTEGER NOT NULL DEFAULT 0,average_duration_ms REAL,last_duration_ms INTEGER,latest_article_at TEXT,etag TEXT,last_modified TEXT,circuit_open_until TEXT,last_error TEXT,last_metrics_json TEXT);""")
        article_columns={row[1] for row in self.db.execute("PRAGMA table_info(articles)")}
        for name in ("image_url", "image_source", "image_checked_at"):
            if name not in article_columns:
                self.db.execute(f"ALTER TABLE articles ADD COLUMN {name} TEXT")
        self.db.commit()
    def upsert_articles(self, articles):
        started=time.perf_counter(); metrics={"new":0,"updated":0,"unchanged":0,"image_metadata_updated":0,"by_source":{}}; changed=[]
        for a in articles:
            normalized_image=canonical_image_url(a.image_url,a.url) if a.image_url else None
            if normalized_image:
                a.image_url=normalized_image
            tags=','.join(a.source_tags)
            fields=(a.source_id,a.source_name,a.title,a.description,a.url,a.canonical_url,iso(a.published_at),a.language,tags,a.author)
            previous=self.db.execute("SELECT source_id,source_name,title,description,url,canonical_url,published_at,language,categories,author,image_url,image_source,image_checked_at FROM articles WHERE article_id=?",(a.article_id,)).fetchone()
            source=metrics["by_source"].setdefault(a.source_id,{"new":0,"updated":0,"unchanged":0})
            if previous is None:
                metrics["new"]+=1; source["new"]+=1; changed.append(a)
            elif tuple(previous[:10])!=fields:
                metrics["updated"]+=1; source["updated"]+=1; changed.append(a)
            else:
                metrics["unchanged"]+=1; source["unchanged"]+=1
                if a.image_url is None: a.image_url=previous["image_url"]
                if a.image_source is None: a.image_source=previous["image_source"]
                if a.image_checked_at is None: a.image_checked_at=previous["image_checked_at"]
                if tuple(previous[10:])!=(a.image_url,a.image_source,a.image_checked_at):
                    metrics["image_metadata_updated"]+=1
                    changed.append(a)
            self.db.execute("""INSERT INTO articles(article_id,source_id,source_name,title,description,url,canonical_url,published_at,collected_at,language,categories,author,image_url,image_source,image_checked_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(article_id) DO UPDATE SET source_id=excluded.source_id,source_name=excluded.source_name,title=excluded.title,description=excluded.description,url=excluded.url,canonical_url=excluded.canonical_url,published_at=COALESCE(excluded.published_at,articles.published_at),collected_at=excluded.collected_at,language=excluded.language,categories=excluded.categories,author=excluded.author,image_url=COALESCE(excluded.image_url,articles.image_url),image_source=COALESCE(excluded.image_source,articles.image_source),image_checked_at=COALESCE(excluded.image_checked_at,articles.image_checked_at)""", (a.article_id,a.source_id,a.source_name,a.title,a.description,a.url,a.canonical_url,iso(a.published_at),iso(a.collected_at),a.language,tags,a.author,a.image_url,a.image_source,a.image_checked_at))
        self.db.commit(); metrics['persistence_ms']=int((time.perf_counter()-started)*1000); return metrics,changed
    def normalize_existing_image_urls(self):
        """Normalize known image negotiation URLs without touching article content."""
        changed=[]
        for row in self.db.execute("SELECT * FROM articles WHERE image_url IS NOT NULL").fetchall():
            normalized=canonical_image_url(row["image_url"],row["url"])
            if normalized and normalized!=row["image_url"]:
                self.db.execute("UPDATE articles SET image_url=? WHERE article_id=?",(normalized,row["article_id"]))
                article=article_from_row({**dict(row),"image_url":normalized})
                changed.append(article)
        if changed: self.db.commit()
        return changed
    def changed_articles(self, article_ids):
        if not article_ids: return []
        rows=[]
        for start in range(0,len(article_ids),500):
            batch=article_ids[start:start+500]; marks=','.join('?' for _ in batch)
            rows.extend(self.db.execute(f"SELECT * FROM articles WHERE article_id IN ({marks})",batch))
        return [article_from_row(row) for row in rows]
    def articles_needing_image(self, limit=12):
        rows=self.db.execute("SELECT * FROM articles WHERE (image_url IS NULL AND (image_checked_at IS NULL OR image_checked_at < datetime('now','-30 days'))) OR lower(image_url) LIKE '%/mascot.%' OR lower(image_url) LIKE '%/mascot/%' OR lower(image_url) LIKE '%/new-reading.%' OR lower(image_url) LIKE '%/new-waving.%' OR lower(image_url) LIKE '%/new-sunrise.%' OR lower(image_url) LIKE '%/new-celebrate.%' OR lower(image_url) LIKE '%/article-fallback.%' OR lower(image_url) LIKE '%/category-image.%' OR lower(image_url) LIKE '%/category-image-%' OR lower(image_url) LIKE '%/category-image/%' OR lower(image_url) LIKE '%/category-photo.%' OR lower(image_url) LIKE '%/category-photo-%' OR lower(image_url) LIKE '%/category-photo/%' OR lower(image_url) LIKE '%/placeholder.%' OR lower(image_url) LIKE '%/placeholder/%' OR lower(image_url) LIKE '%/generic.%' OR lower(image_url) LIKE '%/generic/%' OR lower(image_url) LIKE '%/default-image.%' OR lower(image_url) LIKE '%/random.%' OR lower(image_url) LIKE '%/favicon.%' OR lower(image_url) LIKE '%/favicon/%' OR lower(image_url) LIKE '%/favicons/%' OR lower(image_url) LIKE '%/logo.%' OR lower(image_url) LIKE '%/logo/%' OR lower(image_url) LIKE '%/logos/%' OR lower(image_url) LIKE '%/branding/%' OR (image_source LIKE 'rss:%' AND (image_checked_at IS NULL OR image_checked_at < datetime('now','-30 days'))) OR (image_source LIKE 'html:%' AND image_checked_at < datetime('now','-90 days')) ORDER BY COALESCE(published_at,collected_at) DESC LIMIT ?",(max(1,min(int(limit),1000)),)).fetchall()
        return [article_from_row(row) for row in rows]
    def save_article_image(self, article_id, image_url, image_source, checked_at):
        self.db.execute("UPDATE articles SET image_url=?,image_source=?,image_checked_at=? WHERE article_id=?",(image_url,image_source,checked_at,article_id))
        self.db.commit()
    def get_source_health(self):
        return {row["source_id"]:dict(row) for row in self.db.execute("SELECT * FROM source_health")}
    def save_source_result(self, source_id, metrics, validators=None, error=None, now=None):
        from datetime import datetime, timezone, timedelta
        now=now or datetime.now(timezone.utc).isoformat(); validators=validators or {}
        previous=self.db.execute("SELECT consecutive_failures,average_duration_ms FROM source_health WHERE source_id=?",(source_id,)).fetchone()
        error_text=str(error or "")
        environment_blocked=bool(error_text) and ("[WinError 10013]" in error_text or "operation not permitted" in error_text.lower())
        failed=bool(error) and not environment_blocked
        prior_failures=int(previous[0] or 0) if previous else 0
        failures=prior_failures+1 if failed else (prior_failures if environment_blocked else 0)
        old_average=float(previous[1] or 0) if previous else 0
        duration=int(metrics.get("duration_ms") or 0); average=duration if not old_average else old_average*.8+duration*.2
        open_until=None
        if failures>=3: open_until=(datetime.now(timezone.utc)+timedelta(minutes=min(360,5*(2**min(6,failures-3))))).isoformat()
        status="BLOCKED" if environment_blocked else metrics.get("status")
        self.db.execute("""INSERT INTO source_health(source_id,last_status,last_success_at,last_failure_at,consecutive_failures,average_duration_ms,last_duration_ms,latest_article_at,etag,last_modified,circuit_open_until,last_error,last_metrics_json)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET last_status=excluded.last_status,last_success_at=COALESCE(excluded.last_success_at,source_health.last_success_at),last_failure_at=COALESCE(excluded.last_failure_at,source_health.last_failure_at),consecutive_failures=excluded.consecutive_failures,average_duration_ms=excluded.average_duration_ms,last_duration_ms=excluded.last_duration_ms,latest_article_at=COALESCE(excluded.latest_article_at,source_health.latest_article_at),etag=COALESCE(excluded.etag,source_health.etag),last_modified=COALESCE(excluded.last_modified,source_health.last_modified),circuit_open_until=excluded.circuit_open_until,last_error=excluded.last_error,last_metrics_json=excluded.last_metrics_json""",
          (source_id,status,now if not error else None,now if failed else None,failures,average,duration,metrics.get("newest_article"),validators.get("etag"),validators.get("last_modified"),open_until,error,json.dumps({**metrics,"status":status},ensure_ascii=False)))
        self.db.commit()
    def all_articles(self): return [article_from_row(r) for r in self.db.execute("SELECT * FROM articles ORDER BY COALESCE(published_at,collected_at) DESC")]
    def save_run(self, stats): self.db.execute("INSERT INTO runs(generated_at,stats_json) VALUES(datetime('now'),?)", (json.dumps(stats),)); self.db.commit()

