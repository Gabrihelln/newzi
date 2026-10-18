"""Reusable article index and deterministic, source-grounded profile composition."""
import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone

from newzi_engine.collectors.registry import load_sources
from newzi_engine.processors.classify import classify_for_index, CLASSIFIER_VERSION
from newzi_engine.storage import Store
from newzi_engine.topic_registry import taxonomy
from .timeutil import iso, now_iso, parse

INDEX_VERSION = "content-index-v1"
# Users with many interests get a longer briefing (up to this size) instead of losing topics.
MAX_EXPANDED_BRIEFING_SIZE = 20
# Outlets listed for one story: the chosen article plus others covering the same event.
MAX_SOURCES_PER_ITEM = 5
# A daily briefing tells what is new: older stories only fill a topic's gap inside this window
# (it used to be 30 days, which let last week's previews of games and votes come back).
DEFAULT_BRIEFING_MAX_AGE_HOURS = 48
# Within one event, coverage published this close to its newest article counts as its current state.
LEAD_FRESHNESS_WINDOW = timedelta(hours=3)


def briefing_max_age():
    return timedelta(hours=max(12, int(os.getenv("BRIEFING_MAX_AGE_HOURS", DEFAULT_BRIEFING_MAX_AGE_HOURS))))


def _told_at(repo, profile_key, briefing_date, now, user_id=None):
    """When earlier briefings last told each event or article (manual refreshes included).

    With a user, that user's own briefings, whatever profile they had then (editions delivered
    before editions became per-user count through the user's deliveries); without one, the profile's.
    """
    told = {}
    if user_id:
        owner = "(e.user_id=? OR e.id IN (SELECT edition_id FROM user_briefing_deliveries WHERE user_id=?))"
        owner_params = (user_id, user_id)
    else:
        owner = "(e.profile_key=? OR e.profile_key LIKE ?)"
        owner_params = (profile_key, profile_key + "_manual_%")
    for row in repo.db.execute("""SELECT i.event_id,i.sources_json,e.generated_at FROM briefing_edition_items i
        JOIN briefing_editions e ON e.id=i.edition_id
        WHERE """ + owner + " AND e.edition_date>=? AND e.edition_date<?",
        (*owner_params, (now - timedelta(days=7)).date().isoformat(), briefing_date)):
        if not row["generated_at"]:
            continue
        moment = parse(row["generated_at"])
        keys = [row["event_id"]] + [source.get("article_id") for source in json.loads(row["sources_json"] or "[]")]
        for key in filter(None, keys):
            told[key] = max(told.get(key, moment), moment)
    return told


def _event_lead(members, language, since=None):
    """The article that tells an event's latest state: its newest coverage (after ``since`` when given),
    the briefing's language and the best outlet breaking near-ties.

    A preview ("the match is tonight") and the result clustered into one event must lead with the result.
    """
    pool = [member for member in members if since is None or parse(member["published_at"]) > since] or members
    newest = max(parse(member["published_at"]) for member in pool)
    current = [member for member in pool if parse(member["published_at"]) >= newest - LEAD_FRESHNESS_WINDOW]
    same = [member for member in current
            if str(member["source_language"] or "").split("-")[0].lower() == language.split("-")[0].lower()]
    return max(same or current, key=lambda member: (member["quality_score"], member["published_at"], member["id"]))


def classification_registry_hash(registry=None):
    registry = registry or taxonomy()
    scoring_nodes = {node_id: {"active": bool(node.get("active", True)), "parent_id": node.get("parent_id"), "terms": node.get("terms", {})}
                     for node_id, node in registry.nodes.items()}
    payload = {"classifier_version": CLASSIFIER_VERSION, "nodes": scoring_nodes}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def sync_content(repo, articles=None, ingestion_run_id=None, advance_revision=True):
    """Index changed articles once; unchanged hashes are cache hits across profiles."""
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
        published_iso = iso(published) if published else None
        seen_iso = iso(article.collected_at or datetime.now(timezone.utc))
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
        classification_started=time.perf_counter()
        classification = classify_for_index(article, sources.get(article.source_id, {}).get("categories", []))
        classification_ms+=int((time.perf_counter()-classification_started)*1000)
        tags = classification["tags"]
        stored_image_url = article.image_url or (previous["image_url"] if previous else None)
        stored_image_source = article.image_source or (previous["image_source"] if previous else None)
        stored_image_checked = article.image_checked_at or (previous["image_checked_at"] if previous else None)
        repo.db.execute("""INSERT INTO indexed_content
            (id,content_hash,title,description,url,source_name,source_id,source_country,source_language,published_at,image_url,image_source,image_checked_at,indexed_at,enrichment_mode,taxonomy_hash,quality_score,first_seen_at,last_seen_at,ingested_at,ingestion_run_id,event_id)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET content_hash=excluded.content_hash,title=excluded.title,description=excluded.description,url=excluded.url,source_name=excluded.source_name,source_id=excluded.source_id,source_country=excluded.source_country,source_language=excluded.source_language,published_at=excluded.published_at,image_url=excluded.image_url,image_source=excluded.image_source,image_checked_at=excluded.image_checked_at,indexed_at=excluded.indexed_at,enrichment_mode=excluded.enrichment_mode,taxonomy_hash=excluded.taxonomy_hash,quality_score=excluded.quality_score,first_seen_at=excluded.first_seen_at,last_seen_at=excluded.last_seen_at,ingested_at=excluded.ingested_at,ingestion_run_id=excluded.ingestion_run_id,event_id=excluded.event_id""", (
            article.article_id, digest, article.title, article.description or "", article.url,
            article.source_name, article.source_id, country,
            article.language, published_iso, stored_image_url, stored_image_source, stored_image_checked,
            seen_iso, "DETERMINISTIC_FALLBACK", taxonomy_hash, quality, previous["first_seen_at"] if previous else seen_iso, seen_iso, seen_iso, ingestion_run_id or (repo.db.execute("SELECT ingestion_run_id FROM indexed_content WHERE id=?",(article.article_id,)).fetchone() or [None])[0], previous["event_id"] if previous else None))
        repo.db.execute("UPDATE indexed_content SET classification_confidence=?,classification_reason=? WHERE id=?", (classification["confidence"], classification["reason"], article.article_id))
        repo.db.execute("DELETE FROM content_taxonomy WHERE content_id=?", (article.article_id,))
        repo.db.execute("DELETE FROM content_enrichment WHERE content_id=? AND content_hash<>?", (article.article_id,digest))
        repo.db.executemany("INSERT INTO content_taxonomy(content_id,taxonomy_id,score) VALUES(?,?,?)", [(article.article_id, node_id, score) for node_id, score in tags])
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
        repo.db.execute("UPDATE content_index_state SET value=?,updated_at=? WHERE key='content_revision'",(str(current_revision),now_iso()))
        repo.db.commit()
    metrics["content_revision_before"] = current_revision - bool(metrics["public_content_changed"] and advance_revision)
    metrics["content_revision_after"] = current_revision
    metrics["classification_ms"]=classification_ms
    metrics["index_total_ms"]=int((time.perf_counter()-total_started)*1000)
    metrics["average_article_processing_ms"]=round(metrics["index_total_ms"]/max(1,metrics["articles_seen"]),2)
    return metrics


def sync_article_image_metadata(repo, articles, allow_clear=False):
    """Update only image metadata for indexed IDs; never reclassify article content.

    ``allow_clear`` publishes a verified "no valid image" result (a broken or
    source-wide generic picture was rejected) instead of keeping the stale URL.
    """
    changed = 0; public_changed = 0
    for article in articles:
        if not article.image_url and not (allow_clear and article.image_checked_at):
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
        repo.db.execute("INSERT INTO content_index_state(key,value,updated_at) VALUES('content_revision',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",(str(next_revision),now_iso()))
    repo.db.commit()
    return changed


def sync_content_incremental(repo, changed_articles, ingestion_run_id=None):
    """Index only changed source items, rebuilding once when the taxonomy/version changes."""
    registry=taxonomy()
    taxonomy_hash=classification_registry_hash(registry)
    state={row['key']:row['value'] for row in repo.db.execute("SELECT key,value FROM content_index_state")}
    rebuild=state.get('taxonomy_hash')!=taxonomy_hash or state.get('index_version')!=INDEX_VERSION
    missing=[] if rebuild else unindexed_recent_articles(repo)
    if missing:
        # Stories the engine stored outside this worker (a CLI run, a crash after collection) are not
        # "changed" any more, so they would never reach the index without this reconciliation.
        known={article.article_id for article in changed_articles}
        changed_articles=list(changed_articles)+[article for article in missing if article.article_id not in known]
    articles=Store().all_articles() if rebuild else list(changed_articles)
    metrics=sync_content(repo,articles,ingestion_run_id=ingestion_run_id,advance_revision=False)
    metrics['reconciled_articles']=len(missing)
    from newzi_engine.clustering.events import CLUSTER_VERSION
    if state.get('cluster_version')!=CLUSTER_VERSION:
        cluster_metrics = recluster_content(repo)
        metrics["public_content_changed"] = metrics.get("public_content_changed",0) + cluster_metrics["article_assignments"]
        repo.db.execute("INSERT INTO content_index_state(key,value,updated_at) VALUES('cluster_version',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",(CLUSTER_VERSION,now_iso()))
        repo.db.commit()
    else:
        cluster_metrics = _cluster_incremental_content(repo, changed_articles)
    revision_before=int(metrics.get("content_revision_before",0))
    if metrics.get("public_content_changed"):
        revision_after=revision_before+1
        repo.db.execute("INSERT INTO content_index_state(key,value,updated_at) VALUES('content_revision',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",(str(revision_after),now_iso()))
        repo.db.commit()
    else:
        revision_after=revision_before
    repo.db.execute("INSERT INTO content_index_state(key,value,updated_at) VALUES('taxonomy_hash',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",(taxonomy_hash,now_iso()))
    repo.db.execute("INSERT INTO content_index_state(key,value,updated_at) VALUES('index_version',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",(INDEX_VERSION,now_iso()))
    repo.db.commit()
    metrics['full_rebuild']=rebuild
    metrics['clustering']=cluster_metrics
    metrics['content_revision_after']=revision_after
    return metrics


def unindexed_recent_articles(repo, days=30):
    """Engine articles from the last ``days`` that the product index does not hold."""
    candidates=[article for article in Store().articles_published_since(datetime.now(timezone.utc)-timedelta(days=days))
                if article.title and article.url.startswith(("http://", "https://"))]
    present=set()
    for start in range(0,len(candidates),500):
        ids=[article.article_id for article in candidates[start:start+500]]
        present.update(row["id"] for row in repo.db.execute("SELECT id FROM indexed_content WHERE id IN ("+",".join("?" for _ in ids)+")",ids))
    return [article for article in candidates if article.article_id not in present]


def get_content_revision(repo):
    row=repo.db.execute("SELECT value,updated_at FROM content_index_state WHERE key='content_revision'").fetchone()
    return {"revision":int(row["value"] if row else 0),"updated_at":row["updated_at"] if row else None}


def recluster_content(repo, days=30, chunk_days=3):
    """Re-cluster recent stories from scratch, oldest first, after the merge rules change.

    Event ids are cleared first so stale, over-merged groups cannot pass their id on; each chunk then
    inherits ids from the already re-clustered chunk before it, keeping multi-day stories together.
    """
    from types import SimpleNamespace
    cutoff=datetime.now(timezone.utc)-timedelta(days=days)
    repo.db.execute("UPDATE indexed_content SET event_id=NULL WHERE published_at>=?",(iso(cutoff),))
    repo.db.commit()
    rows=repo.db.execute("SELECT id,published_at FROM indexed_content WHERE published_at>=? ORDER BY published_at,id",(iso(cutoff),)).fetchall()
    stories=[SimpleNamespace(article_id=row["id"],published_at=parse(row["published_at"])) for row in rows]
    totals={"articles_changed":len(stories),"events_touched":0,"events_created":0,"events_updated":0,"article_assignments":0,"full_recluster":True}
    started=time.perf_counter(); index=0
    while index<len(stories):
        chunk_end=stories[index].published_at+timedelta(days=chunk_days)
        chunk=[]
        while index<len(stories) and stories[index].published_at<chunk_end:
            chunk.append(stories[index]); index+=1
        metrics=_cluster_incremental_content(repo,chunk)
        for key in ("events_touched","events_created","events_updated","article_assignments"):
            totals[key]+=metrics.get(key,0)
    totals["clustering_ms"]=round((time.perf_counter()-started)*1000,2)
    return totals


NON_EVENT_GENRES = {"PROMOTION", "EVENT_PROMOTION", "ROUNDUP", "DEAL_COUPON"}


def clustering_genre(article):
    """Coupons, promotions and roundups never form events; everything else clusters as journalism.

    The genre rules are English-only and loose ("best" means a buying guide), so finer genres would
    split real coverage of one story.
    """
    from newzi_engine.editorial.genre import classify_genre
    classify_genre(article)
    return article.content_genre if article.content_genre in NON_EVENT_GENRES else "JOURNALISM"


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
    considered=events_touched=events_created=events_updated=assignments=comparisons=possible_pairs=0
    cluster_phase_ms=0.0; feature_ms=candidate_ms=prune_ms=similarity_ms=0.0
    claimed=set()  # an event split in two keeps its id on one side only
    for group in groups:
        lower=iso(group[0].published_at-window)
        upper=iso(group[-1].published_at+window)
        rows=repo.db.execute("""SELECT c.id,c.title,c.description,c.url,c.source_name,c.source_id,
                c.source_language,c.published_at,c.first_seen_at,c.indexed_at,c.event_id,
                """+repo.db.string_agg("t.taxonomy_id")+""" AS taxonomy_ids
            FROM indexed_content c LEFT JOIN content_taxonomy t ON t.content_id=c.id
            WHERE c.published_at>=? AND c.published_at<=?
            GROUP BY c.id ORDER BY c.published_at,c.id""",(lower,upper)).fetchall()
        articles=[];event_ids={}
        for row in rows:
            published=parse(row["published_at"]) if row["published_at"] else None
            collected=parse((row["first_seen_at"] or row["indexed_at"]))
            article=Article(row["id"],row["source_id"],row["source_name"],row["title"],row["description"] or "",
                row["url"],row["url"],published,collected,row["source_language"] or "en",
                categories=(row["taxonomy_ids"] or "").split(",") if row["taxonomy_ids"] else [],publisher_id=row["source_id"])
            article.content_genre=clustering_genre(article)
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
            prior_ids=sorted({event_ids[item_id] for item_id in members if item_id not in changed_ids and event_ids.get(item_id)} - claimed)
            stable_event_id=prior_ids[0] if prior_ids else event.event_id
            claimed.add(stable_event_id)
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


def compose(repo, topics, language, briefing_size, country_scope="BOTH", now=None, briefing_date=None, user_id=None):
    """Select real indexed articles without running an LLM per user or profile.

    ``briefing_date`` is the edition's local date: briefings of earlier dates count as already told,
    those of ``user_id`` when given.
    """
    registry = taxonomy()
    interests, unknown = registry.canonicalize(topics)
    now = now or datetime.now(timezone.utc)
    briefing_date = briefing_date or now.date().isoformat()
    exact = set(interests)
    descendants = {child for node in exact for child in registry.descendants(node)}
    ancestors = {parent for node in exact for parent in registry.ancestors(node)}
    proximity = {node_id: (0 if node_id in exact else 1 if node_id in descendants else 2 if node_id in ancestors else 3)
                 for node_id in registry.nodes}
    covered_interests = {node_id: sorted((set(registry.ancestors(node_id)) | {node_id}) & exact)
                         for node_id in registry.nodes}
    rows = repo.db.execute("""SELECT c.*, t.taxonomy_id, t.score FROM indexed_content c
        LEFT JOIN content_taxonomy t ON t.content_id=c.id
        WHERE c.published_at>=? AND c.published_at<=? ORDER BY c.published_at DESC""",
        (iso(now-briefing_max_age()), iso(now+timedelta(hours=1)))).fetchall()  # feeds' clocks run a little fast
    by_id = {}
    for row in rows:
        if not _scope_allowed(row["source_country"], country_scope):
            continue
        item = by_id.setdefault(row["id"], {"content": dict(row), "tags": {}})
        if row["taxonomy_id"]:
            item["tags"][row["taxonomy_id"]] = row["score"]
    # Clustering stores one event_id per story covered by several outlets; a briefing tells each story once.
    event_members = {}
    for item in by_id.values():
        event_members.setdefault(item["content"]["event_id"] or item["content"]["id"], []).append(item["content"])
    ranked = []
    from .scheduling import BriefingProfile
    profile_key = BriefingProfile(tuple(interests), language, briefing_size, country_scope).key()
    told_at = _told_at(repo, profile_key, briefing_date, now, user_id)
    # An event told before comes back only with coverage published after it was told (a match
    # previewed yesterday returns with its result); otherwise yesterday's news is not news.
    event_told, event_lead = {}, {}
    for event_id, members in event_members.items():
        told = [told_at[key] for key in (event_id, *(member["id"] for member in members)) if key in told_at]
        event_told[event_id] = max(told) if told else None
        event_lead[event_id] = _event_lead(members, language, since=event_told[event_id])
    def has_update(event_id):
        return any(parse(member["published_at"]) > event_told[event_id] for member in event_members[event_id])
    for item in by_id.values():
        content, tags = item["content"], item["tags"]
        published = parse(content["published_at"])
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
        # Stories already in the briefing language read naturally; others need translation, so they
        # win only within a relevance tier when no same-language story is comparable.
        same_language = str(content["source_language"] or "").split("-")[0].lower() == language.split("-")[0].lower()
        # A story several outlets cover matters more; the bonus stays far below one relevance tier.
        event_id = content["event_id"] or content["id"]
        publishers = len({member["source_id"] for member in event_members[event_id]})
        score = ({"EXACT": 400, "HIERARCHICAL": 300, "BROADER": 200, "GLOBAL": 100}.get(level.removeprefix("EXTENDED_"), 0)
                 + freshness_bonus + match + content["quality_score"] - age_hours/24 + (30 if same_language else 0)
                 + 6 * min(4, publishers - 1))
        primary = primary_taxonomy(tags, interests, registry, proximity)
        interest_matches = sorted({interest for node_id in tags for interest in covered_interests.get(node_id, ())})
        primary_matches = covered_interests.get(primary["id"], ()) if primary else ()
        coverage_interest = max(primary_matches, key=lambda node: (len(registry.ancestors(node)), node), default=None)
        told = event_told[event_id] is not None
        ranked.append({"score": score, "level": level, "content": content, "tags": tags, "event_id": event_id,
                       "stale": told and not has_update(event_id), "update": told and has_update(event_id),
                       "primary": primary, "interest_matches": interest_matches,
                       "coverage_interest": coverage_interest})
    ranked.sort(key=lambda candidate: (-candidate["score"], candidate["content"]["id"]))
    # Stories already told with nothing new are left out; they return only if nothing else is left.
    ranked = [candidate for candidate in ranked if not candidate["stale"]] or ranked
    selected, sources_seen, topics_seen, interests_seen, events_seen = [], {}, {}, set(), set()
    remaining = ranked[:]
    max_size = max(briefing_size, MAX_EXPANDED_BRIEFING_SIZE)
    while remaining and len(selected) < max_size:
        def editorial_score(candidate):
            primary = candidate["primary"]
            topic_id = primary["id"] if primary else None
            source_id = candidate["content"]["source_id"]
            new_interests = candidate["coverage_interest"] and candidate["coverage_interest"] not in interests_seen
            return (candidate["score"] + (16 if new_interests else 0)
                    - 7 * min(4, topics_seen.get(topic_id, 0))
                    - 5 * min(4, sources_seen.get(source_id, 0))
                    - (60 if candidate["stale"] else 0))
        # Coverage first: every chosen interest with a matching story gets a slot before
        # high-volume topics fill the rest; `remaining` is score-ordered, so this is that interest's best story.
        uncovered = [value for value in remaining if value["coverage_interest"] and value["coverage_interest"] not in interests_seen
                     and value["level"].removeprefix("EXTENDED_") in ("EXACT", "HIERARCHICAL")]
        # Beyond the chosen size, the briefing only grows to cover interests still missing.
        if len(selected) >= briefing_size and not uncovered:
            break
        if uncovered:
            candidate = uncovered[0]
        else:
            # Diversity can reorder comparable stories, never pull a much weaker one forward.
            comparable = [value for value in remaining if value["score"] >= remaining[0]["score"] - 20]
            candidate = max(comparable, key=lambda value: (editorial_score(value), value["score"], value["content"]["id"]))
        remaining.remove(candidate)
        level, event_id = candidate["level"], candidate["event_id"]
        if event_id in events_seen:
            continue
        # The event is told through its latest coverage, whichever of its articles ranked it.
        content = event_lead[event_id]
        source_id = content["source_id"]
        sources_seen[source_id] = sources_seen.get(source_id, 0) + 1
        primary = candidate["primary"]
        if primary:
            topics_seen[primary["id"]] = topics_seen.get(primary["id"], 0) + 1
        if candidate["coverage_interest"]:
            interests_seen.add(candidate["coverage_interest"])
        events_seen.add(event_id)
        title = content["title"].strip()
        summary = (content["description"] or title).strip()
        provider = "deterministic_fallback"
        warnings = ["FALLBACK_" + level, "__summary_provider__:" + provider]
        # The level carries this candidate's own age (EXTENDED_ = older than 24h).
        if level.startswith("EXTENDED_"):
            warnings.append("FALLBACK_NO_FRESH_CONTENT_FOR_TOPIC")
        if candidate["stale"]:
            warnings.append("FALLBACK_RECENT_EVENT_REUSE")
        if candidate["update"]:
            warnings.append("EVENT_UPDATE")
        # The chosen story leads; other outlets covering the same event follow, best first.
        others, publishers_listed = [], {content["source_id"]}
        for member in sorted(event_members[event_id], key=lambda value: (-value["quality_score"], value["id"])):
            if member["source_id"] not in publishers_listed and len(others) < MAX_SOURCES_PER_ITEM - 1:
                publishers_listed.add(member["source_id"]); others.append(member)
        if language.split("-")[0].lower() != str(content["source_language"] or "").split("-")[0].lower():
            warnings.append("SOURCE_LANGUAGE_FALLBACK")
        selected.append({"event_id": event_id, "headline": title, "summary": summary,
                         "why_it_matters": None, "key_points": [title], "confidence": 0.55,
                         "evidence_quality": "SOURCE_METADATA", "warnings": warnings,
                         "summary_provider": provider,
                         "primary_taxonomy_id": primary["id"] if primary else None,
                         "primary_taxonomy_label": primary["label"] if primary else None,
                         "primary_taxonomy_reason": primary["reason"] if primary else "UNCLASSIFIED",
                         "matched_taxonomy_ids": sorted(candidate["tags"]),
                         "user_interest_matches": candidate["interest_matches"],
                         "image_url": content.get("image_url"),
                         "sources": [{"publisher": source["source_name"], "url": source["url"],
                                      "article_id": source["id"], "published_at": source["published_at"],
                                      "image_url": source.get("image_url")} for source in (content, *others)]})
    return {"status": "READY" if selected else "FAILED", "generated_at": iso(now),
            "engine_version": INDEX_VERSION, "items": selected,
            "fallback_distribution": {level: sum("FALLBACK_" + level in x["warnings"] for x in selected) for level in {r["level"] for r in ranked}},
            "unknown_taxonomy_ids": unknown}


def taxonomy_health(repo, now=None):
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
        recent = [r for r in match if r["published_at"] and r["published_at"] >= iso(now-timedelta(hours=24))]
        extended = [r for r in match if r["published_at"] and r["published_at"] >= iso(now-timedelta(days=30))]
        rows.append({"id": node["id"], "parent_id": node["parent_id"], "current_valid_content_count": len(match),
                     "content_last_24h": len(recent), "content_extended_window": len(extended),
                     "top_sources": sorted({r["source_id"] for r in extended})[:5],
                     "configured_source_count": len(sources_by_node[node["id"]]),
                     "average_classification_score": round(sum(r["score"] for r in match)/len(match), 2) if match else 0,
                     "coverage_status": "CURRENT" if recent else "EXTENDED" if extended else "NONE"})
    observations={row["name"]:row["count"] for row in repo.db.execute("SELECT name,count FROM taxonomy_resolution_metrics")}
    user_rows=repo.db.execute("SELECT topics_json FROM user_preferences").fetchall()
    profile_sizes=[len(taxonomy().canonicalize(json.loads(row["topics_json"]))[0]) for row in user_rows]
    fallback_counts={"hierarchical_fallback_count":0,"global_fallback_count":0}
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
