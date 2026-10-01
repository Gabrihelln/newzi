"""Reusable article index and deterministic, source-grounded profile composition."""
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone

from newzi_engine.collectors.registry import load_sources
from newzi_engine.processors.classify import classify_article, CLASSIFIER_VERSION
from newzi_engine.storage import Store
from newzi_engine.topic_registry import taxonomy
from newzi_engine.paths import ENGINE_OUTPUT

INDEX_VERSION = "content-index-v1"


def classification_registry_hash(registry=None):
    registry = registry or taxonomy()
    scoring_nodes = {node_id: {"active": bool(node.get("active", True)), "parent_id": node.get("parent_id"), "terms": node.get("terms", {})}
                     for node_id, node in registry.nodes.items()}
    payload = {"classifier_version": CLASSIFIER_VERSION, "nodes": scoring_nodes}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def ensure_content_schema(repo):
    repo.db.executescript("""
    CREATE TABLE IF NOT EXISTS indexed_content(
      id TEXT PRIMARY KEY, content_hash TEXT NOT NULL, title TEXT NOT NULL,
      description TEXT NOT NULL, url TEXT NOT NULL, source_name TEXT NOT NULL,
      source_id TEXT NOT NULL, source_country TEXT, source_language TEXT,
      published_at TEXT, image_url TEXT, image_source TEXT, image_checked_at TEXT,
      indexed_at TEXT NOT NULL, enrichment_mode TEXT NOT NULL,
      first_seen_at TEXT, last_seen_at TEXT, ingested_at TEXT, ingestion_run_id TEXT,
      event_id TEXT);
    CREATE TABLE IF NOT EXISTS content_taxonomy(
      content_id TEXT NOT NULL REFERENCES indexed_content(id) ON DELETE CASCADE,
      taxonomy_id TEXT NOT NULL, score REAL NOT NULL,
      PRIMARY KEY(content_id,taxonomy_id));
    CREATE INDEX IF NOT EXISTS idx_content_taxonomy_node ON content_taxonomy(taxonomy_id,score);
    CREATE INDEX IF NOT EXISTS idx_content_published ON indexed_content(published_at);
    CREATE TABLE IF NOT EXISTS content_enrichment(
      content_id TEXT NOT NULL,content_hash TEXT NOT NULL,prompt_version TEXT NOT NULL,
      schema_version TEXT NOT NULL,generator_version TEXT NOT NULL,output_language TEXT NOT NULL,
      event_id TEXT NOT NULL,headline TEXT NOT NULL,summary TEXT NOT NULL,
      key_points_json TEXT NOT NULL,why_it_matters TEXT,confidence REAL,
      PRIMARY KEY(content_id,content_hash,prompt_version,schema_version,generator_version,output_language));
    CREATE INDEX IF NOT EXISTS idx_enrichment_lookup ON content_enrichment(content_id,content_hash,output_language);
    CREATE TABLE IF NOT EXISTS content_index_state(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL);
    """)
    columns={row[1] for row in repo.db.execute("PRAGMA table_info(indexed_content)")}
    for name in ("image_url", "image_source", "image_checked_at"):
        if name not in columns:
            repo.db.execute(f"ALTER TABLE indexed_content ADD COLUMN {name} TEXT")
    if "taxonomy_hash" not in columns:
        repo.db.execute("ALTER TABLE indexed_content ADD COLUMN taxonomy_hash TEXT")
    if "quality_score" not in columns:
        repo.db.execute("ALTER TABLE indexed_content ADD COLUMN quality_score REAL NOT NULL DEFAULT 0")
    for name in ("first_seen_at", "last_seen_at", "ingested_at", "ingestion_run_id"):
        if name not in columns:
            repo.db.execute(f"ALTER TABLE indexed_content ADD COLUMN {name} TEXT")
    if "event_id" not in columns:
        repo.db.execute("ALTER TABLE indexed_content ADD COLUMN event_id TEXT")
    repo.db.execute("CREATE INDEX IF NOT EXISTS idx_content_event_published ON indexed_content(event_id,published_at)")
    repo.db.execute("UPDATE indexed_content SET first_seen_at=COALESCE(first_seen_at,indexed_at),last_seen_at=COALESCE(last_seen_at,indexed_at),ingested_at=COALESCE(ingested_at,indexed_at)")
    # Older importer versions substituted collected_at for missing source dates.
    # Values effectively identical to index time are not trustworthy publication dates.
    repo.db.execute("UPDATE indexed_content SET published_at=NULL WHERE published_at IS NOT NULL AND indexed_at IS NOT NULL AND datetime(indexed_at)<datetime('now','-1 day') AND ABS((julianday(published_at)-julianday(indexed_at))*86400)<1")
    repo.db.execute("INSERT OR IGNORE INTO content_index_state(key,value,updated_at) VALUES('content_revision','0',?)",(datetime.now(timezone.utc).isoformat(),))
    repo.db.commit()


def sync_content(repo, articles=None, ingestion_run_id=None, advance_revision=True):
    """Index changed articles once; unchanged hashes are cache hits across profiles."""
    ensure_content_schema(repo)
    articles = Store().all_articles() if articles is None else articles
    sources = {source["id"]: source for source in load_sources()}
    countries = {source_id: source.get("country", "") for source_id, source in sources.items()}
    registry = taxonomy()
    taxonomy_hash = classification_registry_hash(registry)
    total_started=time.perf_counter(); classification_ms=0
    current_revision = int((repo.db.execute("SELECT value FROM content_index_state WHERE key='content_revision'").fetchone() or ["0"])[0])
    metrics = {"articles_seen": 0, "classification_count": 0, "cache_hits": 0,
               "articles_new": 0, "articles_updated": 0, "articles_unchanged": 0,
               "public_content_changed": 0}
    for article in articles:
        if not article.url.startswith(("http://", "https://")) or not article.title:
            continue
        metrics["articles_seen"] += 1
        # Collection time is provenance, not publication time. Keep unknown source
        # dates unknown so ingestion cannot make old stories look new.
        published = article.published_at
        published_iso = published.astimezone(timezone.utc).isoformat() if published else None
        seen_iso = (article.collected_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        country = countries.get(article.source_id, "")
        quality = min(10.0, float(sources.get(article.source_id, {}).get("priority", 5))) + min(5.0, len(article.description or "") / 80)
        digest = hashlib.sha256(json.dumps([INDEX_VERSION, article.title, article.description, article.url, article.language], ensure_ascii=False).encode()).hexdigest()
        previous = repo.db.execute("SELECT content_hash,taxonomy_hash,source_name,source_id,source_country,published_at,quality_score,first_seen_at,event_id,image_url,image_source,image_checked_at FROM indexed_content WHERE id=?", (article.article_id,)).fetchone()
        if previous and previous["content_hash"] == digest and previous["taxonomy_hash"] == taxonomy_hash:
            published_iso = published_iso or previous["published_at"]
            repo.db.execute("UPDATE indexed_content SET source_name=?,source_id=?,source_country=?,published_at=?,image_url=COALESCE(?,image_url),image_source=COALESCE(?,image_source),image_checked_at=COALESCE(?,image_checked_at),quality_score=?,last_seen_at=?,ingested_at=?,ingestion_run_id=COALESCE(?,ingestion_run_id) WHERE id=?",(article.source_name,article.source_id,country,published_iso,article.image_url,article.image_source,article.image_checked_at,quality,seen_iso,seen_iso,ingestion_run_id,article.article_id))
            metrics["cache_hits"] += 1
            metrics["articles_unchanged"] += 1
            continue
        classification_started=time.perf_counter(); _, scores = classify_article(article); classification_ms+=int((time.perf_counter()-classification_started)*1000)
        tags = [(node_id, float(score)) for node_id, score in scores.items() if score >= 4 and registry.resolve(node_id)]
        for node_id in article.categories:
            canonical = registry.resolve(node_id)
            if canonical and canonical not in {tag[0] for tag in tags}:
                tags.append((canonical, 4.0))
        stored_image_url = article.image_url or (previous["image_url"] if previous else None)
        stored_image_source = article.image_source or (previous["image_source"] if previous else None)
        stored_image_checked = article.image_checked_at or (previous["image_checked_at"] if previous else None)
        repo.db.execute("""INSERT OR REPLACE INTO indexed_content
            (id,content_hash,title,description,url,source_name,source_id,source_country,source_language,published_at,image_url,image_source,image_checked_at,indexed_at,enrichment_mode,taxonomy_hash,quality_score,first_seen_at,last_seen_at,ingested_at,ingestion_run_id,event_id)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            article.article_id, digest, article.title, article.description or "", article.url,
            article.source_name, article.source_id, country,
            article.language, published_iso, stored_image_url, stored_image_source, stored_image_checked,
            seen_iso, "DETERMINISTIC_FALLBACK", taxonomy_hash, quality, previous["first_seen_at"] if previous else seen_iso, seen_iso, seen_iso, ingestion_run_id or (repo.db.execute("SELECT ingestion_run_id FROM indexed_content WHERE id=?",(article.article_id,)).fetchone() or [None])[0], previous["event_id"] if previous else None))
        repo.db.execute("DELETE FROM content_taxonomy WHERE content_id=?", (article.article_id,))
        repo.db.execute("DELETE FROM content_enrichment WHERE content_id=? AND content_hash<>?", (article.article_id,digest))
        repo.db.executemany("INSERT INTO content_taxonomy VALUES(?,?,?)", [(article.article_id, node_id, score) for node_id, score in tags])
        metrics["classification_count"] += 1
        if published_iso:
            if previous:
                metrics["articles_updated"] += 1
            else:
                metrics["articles_new"] += 1
            metrics["public_content_changed"] += 1
    repo.db.commit()
    if metrics["public_content_changed"] and advance_revision:
        current_revision += 1
        repo.db.execute("UPDATE content_index_state SET value=?,updated_at=? WHERE key='content_revision'",(str(current_revision),datetime.now(timezone.utc).isoformat()))
        repo.db.commit()
    metrics["content_revision_before"] = current_revision - bool(metrics["public_content_changed"] and advance_revision)
    metrics["content_revision_after"] = current_revision
    metrics["classification_ms"]=classification_ms
    metrics["index_total_ms"]=int((time.perf_counter()-total_started)*1000)
    metrics["average_article_processing_ms"]=round(metrics["index_total_ms"]/max(1,metrics["articles_seen"]),2)
    return metrics


def sync_article_image_metadata(repo, articles):
    """Update only image metadata for indexed IDs; never reclassify article content."""
    ensure_content_schema(repo)
    changed = 0; public_changed = 0
    for article in articles:
        if not article.image_url:
            continue
        previous = repo.db.execute("SELECT image_url,image_source,image_checked_at,published_at FROM indexed_content WHERE id=?",(article.article_id,)).fetchone()
        if not previous or tuple(previous[:3]) == (article.image_url,article.image_source,article.image_checked_at):
            continue
        cursor = repo.db.execute("UPDATE indexed_content SET image_url=?,image_source=?,image_checked_at=? WHERE id=?", (article.image_url, article.image_source, article.image_checked_at, article.article_id))
        changed += cursor.rowcount
        if previous and previous["published_at"] and previous["image_url"] != article.image_url: public_changed += cursor.rowcount
    if public_changed:
        revision=repo.db.execute("SELECT value FROM content_index_state WHERE key='content_revision'").fetchone()
        next_revision=int(revision[0] if revision else 0)+1
        repo.db.execute("INSERT INTO content_index_state(key,value,updated_at) VALUES('content_revision',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",(str(next_revision),datetime.now(timezone.utc).isoformat()))
    repo.db.commit()
    return changed


def sync_content_incremental(repo, changed_articles, ingestion_run_id=None):
    """Index only changed source items, rebuilding once when the taxonomy/version changes."""
    ensure_content_schema(repo)
    registry=taxonomy()
    taxonomy_hash=classification_registry_hash(registry)
    state={row['key']:row['value'] for row in repo.db.execute("SELECT key,value FROM content_index_state")}
    rebuild=state.get('taxonomy_hash')!=taxonomy_hash or state.get('index_version')!=INDEX_VERSION
    articles=Store().all_articles() if rebuild else list(changed_articles)
    metrics=sync_content(repo,articles,ingestion_run_id=ingestion_run_id,advance_revision=False)
    cluster_metrics = _cluster_incremental_content(repo, changed_articles)
    revision_before=int(metrics.get("content_revision_before",0))
    if metrics.get("public_content_changed"):
        revision_after=revision_before+1
        repo.db.execute("INSERT INTO content_index_state(key,value,updated_at) VALUES('content_revision',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",(str(revision_after),datetime.now(timezone.utc).isoformat()))
        repo.db.commit()
    else:
        revision_after=revision_before
    repo.db.execute("INSERT INTO content_index_state(key,value,updated_at) VALUES('taxonomy_hash',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",(taxonomy_hash,datetime.now(timezone.utc).isoformat()))
    repo.db.execute("INSERT INTO content_index_state(key,value,updated_at) VALUES('index_version',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",(INDEX_VERSION,datetime.now(timezone.utc).isoformat()))
    repo.db.commit()
    metrics['full_rebuild']=rebuild
    metrics['clustering']=cluster_metrics
    metrics['content_revision_after']=revision_after
    return metrics


def get_content_revision(repo):
    # This lightweight read endpoint must work even before the content index is
    # created and must not attempt a data migration on legacy schema variants.
    repo.db.execute("CREATE TABLE IF NOT EXISTS content_index_state(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL)")
    row=repo.db.execute("SELECT value,updated_at FROM content_index_state WHERE key='content_revision'").fetchone()
    return {"revision":int(row["value"] if row else 0),"updated_at":row["updated_at"] if row else None}


def _cluster_incremental_content(repo, changed_articles):
    """Cluster changed stories with only their publication-time neighborhood."""
    started=time.perf_counter()
    changed_ids={article.article_id for article in changed_articles}
    dated=sorted((article for article in changed_articles if article.published_at),key=lambda article:article.published_at)
    if not dated:
        return {"articles_changed":len(changed_ids),"articles_considered":0,"events_touched":0,
                "events_created":0,"events_updated":0,"article_assignments":0,
                "clustering_ms":0,"window_hours":72}
    from newzi_engine.collectors.registry import load_settings
    from newzi_engine.clustering.events import cluster_articles
    from newzi_engine.models import Article
    from newzi_engine.collectors.registry import load_sources
    settings=load_settings(); window_hours=float(settings.get("clustering",{}).get("time_window_hours",72))
    window=timedelta(hours=window_hours)
    groups=[];current=[];group_start=None
    for article in dated:
        if current and article.published_at-group_start>window:
            groups.append(current);current=[]
        if not current: group_start=article.published_at
        current.append(article)
    if current: groups.append(current)
    priorities={source["id"]:source.get("priority",5) for source in load_sources()}
    considered=events_touched=events_created=events_updated=assignments=comparisons=possible_pairs=0
    cluster_phase_ms=0.0; feature_ms=candidate_ms=prune_ms=similarity_ms=0.0
    for group in groups:
        lower=(group[0].published_at-window).astimezone(timezone.utc).isoformat()
        upper=(group[-1].published_at+window).astimezone(timezone.utc).isoformat()
        rows=repo.db.execute("""SELECT c.id,c.title,c.description,c.url,c.source_name,c.source_id,
                c.source_language,c.published_at,c.first_seen_at,c.indexed_at,c.event_id,
                GROUP_CONCAT(t.taxonomy_id, ',') AS taxonomy_ids
            FROM indexed_content c LEFT JOIN content_taxonomy t ON t.content_id=c.id
            WHERE c.published_at>=? AND c.published_at<=?
            GROUP BY c.id ORDER BY c.published_at,c.id""",(lower,upper)).fetchall()
        articles=[];event_ids={}
        for row in rows:
            published=datetime.fromisoformat(row["published_at"].replace("Z","+00:00")) if row["published_at"] else None
            collected=datetime.fromisoformat((row["first_seen_at"] or row["indexed_at"]).replace("Z","+00:00"))
            article=Article(row["id"],row["source_id"],row["source_name"],row["title"],row["description"] or "",
                row["url"],row["url"],published,collected,row["source_language"] or "en",
                categories=(row["taxonomy_ids"] or "").split(",") if row["taxonomy_ids"] else [],publisher_id=row["source_id"])
            article.content_genre="JOURNALISM"
            articles.append(article);event_ids[article.article_id]=row["event_id"]
        if not articles: continue
        considered+=len(articles)
        phase=time.perf_counter(); events,audit=cluster_articles(articles,settings,load_sources(),diagnostics=True)
        cluster_phase_ms+=(time.perf_counter()-phase)*1000
        metrics=audit.get("metrics",{}); timings=metrics.get("timings_ms",{})
        comparisons+=int(metrics.get("pair_comparisons",0));possible_pairs+=int(metrics.get("possible_pairs",0))
        feature_ms+=float(timings.get("feature_preparation",0));candidate_ms+=float(timings.get("candidate_generation",0))
        prune_ms+=float(timings.get("cheap_pruning",0));similarity_ms+=float(timings.get("full_similarity",0))
        for event in events:
            members=set(event.article_ids)
            if not members & changed_ids: continue
            prior_ids=sorted({event_ids[item_id] for item_id in members if item_id not in changed_ids and event_ids.get(item_id)})
            stable_event_id=prior_ids[0] if prior_ids else event.event_id
            if prior_ids:
                events_updated+=1
            else:
                events_created+=1
            marks=",".join("?" for _ in members)
            repo.db.execute(f"UPDATE indexed_content SET event_id=? WHERE id IN ({marks})",[stable_event_id,*sorted(members)])
            events_touched+=1;assignments+=len(members)
    repo.db.commit()
    return {"articles_changed":len(changed_ids),"articles_considered":considered,"events_touched":events_touched,
            "events_created":events_created,"events_updated":events_updated,
            "article_assignments":assignments,"pair_comparisons":comparisons,"possible_pairs":possible_pairs,
            "timings_ms":{"feature_preparation":round(feature_ms,2),"candidate_generation":round(candidate_ms,2),
                "cheap_pruning":round(prune_ms,2),"full_similarity":round(similarity_ms,2),
                "cluster_total":round(cluster_phase_ms,2)},"clustering_ms":round((time.perf_counter()-started)*1000,2),
            "window_hours":window_hours}


def sync_semantic_output(repo, path=None):
    """Import already validated global phase 3.3 output; never invoke Ollama here."""
    ensure_content_schema(repo)
    path = path or ENGINE_OUTPUT / "daily_briefing_v2.json"
    try:
        output = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return 0
    count = 0
    for item in output.get("items", []):
        if not item.get("headline") or not item.get("summary") or item.get("language_gate") == "FAIL":
            continue
        language = item.get("output_language") or "pt-BR"
        for article_id in item.get("provenance", {}).get("articles", []):
            content = repo.db.execute("SELECT content_hash FROM indexed_content WHERE id=?", (article_id,)).fetchone()
            if not content: continue
            cursor=repo.db.execute("""INSERT OR IGNORE INTO content_enrichment VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (
                article_id, content["content_hash"], "phase33", "daily_briefing_v2",
                item.get("summary_provider", "ollama"), language, item.get("event_id") or article_id,
                item["headline"], item["summary"], json.dumps(item.get("key_points") or []),
                item.get("why_it_matters"), item.get("confidence")))
            count += cursor.rowcount
    repo.db.commit()
    return count


def _scope_allowed(country, scope):
    if scope == "LOCAL":
        return country == "BR"
    if scope == "GLOBAL":
        return country != "BR"
    return True


def candidate_counts(repo, interests):
    registry = taxonomy()
    exact = set(interests)
    hierarchical = exact | {child for node in exact for child in registry.descendants(node)}
    broader = hierarchical | {parent for node in exact for parent in registry.ancestors(node)}
    rows = repo.db.execute("SELECT DISTINCT content_id,taxonomy_id FROM content_taxonomy").fetchall()
    return {
        "exact_candidate_count": len({r["content_id"] for r in rows if r["taxonomy_id"] in exact}),
        "hierarchical_candidate_count": len({r["content_id"] for r in rows if r["taxonomy_id"] in hierarchical}),
        "broader_candidate_count": len({r["content_id"] for r in rows if r["taxonomy_id"] in broader}),
        "global_candidate_count": repo.db.execute("SELECT COUNT(*) FROM indexed_content").fetchone()[0],
    }


def primary_taxonomy(tags, interests, registry=None, proximity=None):
    """Choose one canonical label using interest proximity, weight and specificity."""
    registry = registry or taxonomy()
    exact = set(interests)
    proximity = proximity or {node_id: (0 if node_id in exact else
                                    1 if set(registry.ancestors(node_id)) & exact else
                                    2 if any(node_id in registry.ancestors(interest) for interest in exact) else 3)
                              for node_id in registry.nodes}
    candidates = []
    for node_id, weight in tags.items():
        node = registry.nodes.get(node_id)
        if not node or not node.get("active", True):
            continue
        tier = proximity.get(node_id, 3)
        candidates.append((tier, -float(weight), -len(registry.ancestors(node_id)), node.get("display_order", 0), node_id))
    if not candidates:
        return None
    tier, _, _, _, node_id = min(candidates)
    return {"id": node_id, "label": registry.nodes[node_id]["name"],
            "reason": ("SELECTED_INTEREST", "INTEREST_DESCENDANT", "INTEREST_ANCESTOR", "CLASSIFICATION")[tier]}


def compose(repo, topics, language, briefing_size, country_scope="BOTH", now=None):
    """Select real indexed articles without running an LLM per user or profile."""
    ensure_content_schema(repo)
    registry = taxonomy()
    interests, unknown = registry.canonicalize(topics)
    now = now or datetime.now(timezone.utc)
    exact = set(interests)
    descendants = {child for node in exact for child in registry.descendants(node)}
    ancestors = {parent for node in exact for parent in registry.ancestors(node)}
    proximity = {node_id: (0 if node_id in exact else 1 if node_id in descendants else 2 if node_id in ancestors else 3)
                 for node_id in registry.nodes}
    covered_interests = {node_id: sorted((set(registry.ancestors(node_id)) | {node_id}) & exact)
                         for node_id in registry.nodes}
    rows = repo.db.execute("""SELECT c.*, t.taxonomy_id, t.score FROM indexed_content c
        LEFT JOIN content_taxonomy t ON t.content_id=c.id
        WHERE c.published_at>=? ORDER BY c.published_at DESC""", ((now-timedelta(days=30)).isoformat(),)).fetchall()
    by_id = {}
    for row in rows:
        if not _scope_allowed(row["source_country"], country_scope):
            continue
        item = by_id.setdefault(row["id"], {"content": dict(row), "tags": {}})
        if row["taxonomy_id"]:
            item["tags"][row["taxonomy_id"]] = row["score"]
    ranked = []
    previous_events = set()
    # Editions are shared by profile, so repetition is measured at profile level.
    from .scheduling import BriefingProfile
    profile_key = BriefingProfile(tuple(interests), language, briefing_size, country_scope).key()
    if repo.db.execute("SELECT 1 FROM sqlite_master WHERE name='briefing_editions'").fetchone():
        for row in repo.db.execute("""SELECT i.event_id,i.sources_json FROM briefing_edition_items i
            JOIN briefing_editions e ON e.id=i.edition_id WHERE e.profile_key=? AND e.edition_date>=?""",
            (profile_key, (now-timedelta(days=7)).date().isoformat())):
            if row["event_id"]:
                previous_events.add(row["event_id"])
            previous_events.update(source.get("article_id") for source in json.loads(row["sources_json"] or "[]") if source.get("article_id"))
    for item in by_id.values():
        content, tags = item["content"], item["tags"]
        published = datetime.fromisoformat(content["published_at"].replace("Z", "+00:00"))
        age_hours = max(0, (now-published).total_seconds()/3600)
        if tags.keys() & exact:
            level = "EXACT"
        elif tags.keys() & descendants:
            level = "HIERARCHICAL"
        elif tags.keys() & ancestors:
            level = "BROADER"
        else:
            level = "GLOBAL"
        if age_hours > 24:
            level = "EXTENDED_" + level
        match = max((tags.get(node, 0) for node in exact | descendants | ancestors), default=0)
        # Freshness breaks ties inside an editorial relevance tier without allowing
        # unrelated current stories to outrank a strong match for the user's topic.
        freshness_bonus = 45 if age_hours <= 24 else 20 if age_hours <= 72 else 0
        score = {"EXACT": 400, "HIERARCHICAL": 300, "BROADER": 200, "GLOBAL": 100}.get(level.removeprefix("EXTENDED_"), 0) + freshness_bonus + match + content["quality_score"] - age_hours/24
        primary = primary_taxonomy(tags, interests, registry, proximity)
        interest_matches = sorted({interest for node_id in tags for interest in covered_interests.get(node_id, ())})
        primary_matches = covered_interests.get(primary["id"], ()) if primary else ()
        coverage_interest = max(primary_matches, key=lambda node: (len(registry.ancestors(node)), node), default=None)
        ranked.append({"score": score, "level": level, "content": content, "tags": tags,
                       "primary": primary, "interest_matches": interest_matches,
                       "coverage_interest": coverage_interest})
    ranked.sort(key=lambda candidate: (-candidate["score"], candidate["content"]["id"]))
    selected, sources_seen, topics_seen, interests_seen, events_seen = [], {}, {}, set(), set()
    remaining = ranked[:]
    while remaining and len(selected) < briefing_size:
        def editorial_score(candidate):
            primary = candidate["primary"]
            topic_id = primary["id"] if primary else None
            source_id = candidate["content"]["source_id"]
            new_interests = candidate["coverage_interest"] and candidate["coverage_interest"] not in interests_seen
            return (candidate["score"] + (16 if new_interests else 0)
                    - 7 * min(4, topics_seen.get(topic_id, 0))
                    - 5 * min(4, sources_seen.get(source_id, 0))
                    - (60 if candidate["content"]["id"] in previous_events else 0))
        # Diversity can reorder comparable stories, never pull a much weaker one forward.
        comparable = [value for value in remaining if value["score"] >= remaining[0]["score"] - 20]
        candidate = max(comparable, key=lambda value: (editorial_score(value), value["score"], value["content"]["id"]))
        remaining.remove(candidate)
        level, content = candidate["level"], candidate["content"]
        enriched = repo.db.execute("""SELECT * FROM content_enrichment WHERE content_id=? AND content_hash=? AND output_language=?
            ORDER BY generator_version DESC LIMIT 1""", (content["id"], content["content_hash"], language)).fetchone()
        event_id = enriched["event_id"] if enriched else content["id"]
        if event_id in events_seen:
            continue
        source_id = content["source_id"]
        sources_seen[source_id] = sources_seen.get(source_id, 0) + 1
        primary = candidate["primary"]
        if primary:
            topics_seen[primary["id"]] = topics_seen.get(primary["id"], 0) + 1
        if candidate["coverage_interest"]:
            interests_seen.add(candidate["coverage_interest"])
        events_seen.add(event_id)
        title = (enriched["headline"] if enriched else content["title"]).strip()
        summary = ((enriched["summary"] if enriched else content["description"]) or title).strip()
        provider = enriched["generator_version"] if enriched else "deterministic_fallback"
        warnings = ["FALLBACK_" + level, "__summary_provider__:" + provider]
        if age_hours > 24:
            warnings.append("FALLBACK_NO_FRESH_CONTENT_FOR_TOPIC")
        if content["id"] in previous_events:
            warnings.append("FALLBACK_RECENT_EVENT_REUSE")
        if not enriched and language.split("-")[0].lower() != str(content["source_language"] or "").split("-")[0].lower():
            warnings.append("SOURCE_LANGUAGE_FALLBACK")
        selected.append({"event_id": event_id, "headline": title, "summary": summary,
                         "why_it_matters": enriched["why_it_matters"] if enriched else None,
                         "key_points": json.loads(enriched["key_points_json"]) if enriched else [title],
                         "confidence": enriched["confidence"] if enriched else 0.55,
                         "evidence_quality": "SEMANTIC_CACHE" if enriched else "SOURCE_METADATA", "warnings": warnings,
                         "summary_provider": provider,
                         "primary_taxonomy_id": primary["id"] if primary else None,
                         "primary_taxonomy_label": primary["label"] if primary else None,
                         "primary_taxonomy_reason": primary["reason"] if primary else "UNCLASSIFIED",
                         "matched_taxonomy_ids": sorted(candidate["tags"]),
                         "user_interest_matches": candidate["interest_matches"],
                         "image_url": content.get("image_url"),
                         "sources": [{"publisher": content["source_name"], "url": content["url"],
                                      "article_id": content["id"], "published_at": content["published_at"],
                                      "image_url": content.get("image_url")}]})
    return {"status": "READY" if selected else "FAILED", "generated_at": now.isoformat(),
            "engine_version": INDEX_VERSION, "items": selected,
            "fallback_distribution": {level: sum("FALLBACK_" + level in x["warnings"] for x in selected) for level in {r["level"] for r in ranked}},
            "unknown_taxonomy_ids": unknown}


def taxonomy_health(repo, now=None):
    ensure_content_schema(repo)
    now = now or datetime.now(timezone.utc)
    rows = []
    sources_by_node = {node_id: set() for node_id in taxonomy().nodes}
    for source in load_sources():
        for category in source.get("categories", []):
            node_id = taxonomy().resolve(category, active_only=False)
            if node_id:
                sources_by_node[node_id].add(source["id"])
    for node in taxonomy().rows():
        if not node["enabled"]:
            continue
        match = repo.db.execute("""SELECT c.source_id,c.published_at,t.score FROM content_taxonomy t
            JOIN indexed_content c ON c.id=t.content_id WHERE t.taxonomy_id=?""", (node["id"],)).fetchall()
        recent = [r for r in match if r["published_at"] and r["published_at"] >= (now-timedelta(hours=24)).isoformat()]
        extended = [r for r in match if r["published_at"] and r["published_at"] >= (now-timedelta(days=30)).isoformat()]
        rows.append({"id": node["id"], "parent_id": node["parent_id"], "current_valid_content_count": len(match),
                     "content_last_24h": len(recent), "content_extended_window": len(extended),
                     "top_sources": sorted({r["source_id"] for r in extended})[:5],
                     "configured_source_count": len(sources_by_node[node["id"]]),
                     "average_classification_score": round(sum(r["score"] for r in match)/len(match), 2) if match else 0,
                     "coverage_status": "CURRENT" if recent else "EXTENDED" if extended else "NONE"})
    observations={row["name"]:row["count"] for row in repo.db.execute("SELECT name,count FROM taxonomy_resolution_metrics")} if repo.db.execute("SELECT 1 FROM sqlite_master WHERE name='taxonomy_resolution_metrics'").fetchone() else {}
    user_rows=repo.db.execute("SELECT topics_json FROM user_preferences").fetchall()
    profile_sizes=[len(taxonomy().canonicalize(json.loads(row["topics_json"]))[0]) for row in user_rows]
    fallback_counts={"hierarchical_fallback_count":0,"global_fallback_count":0}
    if repo.db.execute("SELECT 1 FROM sqlite_master WHERE name='briefing_edition_items'").fetchone():
        for item in repo.db.execute("SELECT warnings_json FROM briefing_edition_items"):
            warnings=json.loads(item["warnings_json"])
            if any("HIERARCHICAL" in warning for warning in warnings): fallback_counts["hierarchical_fallback_count"]+=1
            if any("GLOBAL" in warning for warning in warnings): fallback_counts["global_fallback_count"]+=1
    return {"taxonomy_nodes_active": len(rows), "taxonomy_nodes_with_content": sum(r["current_valid_content_count"] > 0 for r in rows),
            "taxonomy_nodes_without_recent_content": sum(r["content_last_24h"] == 0 for r in rows),
            "taxonomy_alias_resolutions":observations.get("taxonomy_alias_resolutions",0),
            "taxonomy_unknown_ids":observations.get("taxonomy_unknown_ids",0),
            "classification_count_by_taxonomy":{row["taxonomy_id"]:row["count"] for row in repo.db.execute("SELECT taxonomy_id,COUNT(*) AS count FROM content_taxonomy GROUP BY taxonomy_id")},
            "user_profile_taxonomy_count":{"users":len(profile_sizes),"average":round(sum(profile_sizes)/len(profile_sizes),2) if profile_sizes else 0},
            **fallback_counts,"inactive_nodes": [node["id"] for node in taxonomy().rows() if not node["enabled"]], "nodes": rows}
