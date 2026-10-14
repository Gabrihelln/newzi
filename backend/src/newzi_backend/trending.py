"""Trending stories ("Em alta"): what many outlets are covering right now, shown to every user.

An event (articles the clustering grouped under one ``event_id``) trends when at least
TRENDING_MIN_SOURCES distinct sources covered it within the last TRENDING_WINDOW_HOURS. Its score adds
one point per source, decayed by how long ago that source joined (half-life about four hours), so
coverage that is growing now outranks coverage that piled up earlier. Deals, guides and explainers
never trend. Unlike the briefing, user topics are ignored; only the country scope applies.
"""
import math
import os
from datetime import timedelta

from .breaking import is_news
from .timeutil import iso, parse, utc_now

DECAY_HOURS = 6.0


def _env_int(name, default):
    return int(os.getenv(name, str(default)))


def _in_scope(countries, scope):
    if scope == "LOCAL":
        return "BR" in countries
    if scope == "GLOBAL":
        return bool(countries - {"BR"})
    return True


def trending_events(repo, country_scope="BOTH", limit=5, now=None):
    """Ranked trending events: dicts with the lead article id, outlet count and score."""
    now = now or utc_now()
    window = timedelta(hours=max(1, _env_int("TRENDING_WINDOW_HOURS", 12)))
    min_sources = max(2, _env_int("TRENDING_MIN_SOURCES", 3))
    rows = repo.db.execute(
        """SELECT id,event_id,title,description,url,source_id,source_country,source_language,published_at,quality_score
           FROM indexed_content WHERE event_id IS NOT NULL AND event_id<>'' AND published_at>=? AND published_at<=?
           ORDER BY published_at,id""", (iso(now - window), iso(now + timedelta(minutes=10)))).fetchall()
    by_event = {}
    for row in rows:
        by_event.setdefault(row["event_id"], []).append(row)
    events = []
    for event_id, articles in by_event.items():
        joined = {}
        for row in articles:  # rows are oldest first: the first article per source is when it joined
            joined.setdefault(row["source_id"], row["published_at"])
        if len(joined) < min_sources or not _in_scope({row["source_country"] for row in articles}, country_scope):
            continue
        lead = sorted(articles, key=lambda row: (row["source_language"] not in ("pt-BR", "pt"), -(row["quality_score"] or 0), row["published_at"]))[0]
        if not is_news(lead["title"], lead["description"], lead["url"]):
            continue
        ages = [max(0.0, (now - parse(published)).total_seconds() / 3600) for published in joined.values()]
        score = sum(math.exp(-age / DECAY_HOURS) for age in ages)
        events.append({"event_id": event_id, "lead_id": lead["id"], "outlets": len(joined), "score": round(score, 3)})
    events.sort(key=lambda event: (-event["score"], -event["outlets"], event["event_id"]))
    return events[:limit]


def trending_stories(repo, uid, limit=5, now=None):
    """Trending events as news items for ``uid`` (labels follow their interests), most trending first."""
    prefs = repo.get_preferences(uid) or {}
    items = []
    for rank, event in enumerate(trending_events(repo, prefs.get("country_scope") or "BOTH", limit, now), 1):
        item = repo.story(uid, event["lead_id"])
        if item:
            items.append({**item, "position": rank, "trending": {"rank": rank, "outlets": event["outlets"]}})
    return items
