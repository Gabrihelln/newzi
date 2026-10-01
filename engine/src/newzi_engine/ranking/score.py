from datetime import datetime, timezone
import math

def rank_events(events, sources, settings):
    weights = settings.get("ranking", {}); by_id = {s["id"]: s for s in sources}; now = datetime.now(timezone.utc)
    for e in events:
        e.topic_relevance = 0 if e.categories == ["OTHER"] else min(100, 60 + 15 * len(e.categories))
        priorities = [by_id.get(s, {}).get("priority", 5) for s in set(e.source_ids)]; types = [by_id.get(s, {}).get("source_type", "JOURNALISM") for s in set(e.source_ids)]
        e.source_quality = min(100, sum(priorities) / max(1, len(priorities)) * 10 + (5 if "PRIMARY" in types else 0)); e.source_diversity = min(100, len(set(e.publisher_ids or e.source_ids)) / 4 * 100); age = max(0, (now - (e.published_at or e.last_seen_at)).total_seconds() / 86400); e.recency = 100 * math.exp(-age / 3); e.coverage = min(100, len(e.articles) / 4 * 100)
        genre = e.content_genre
        e.newsworthiness_score = 85 if genre in {"BREAKING_NEWS", "FUNDING", "REGULATION", "RESEARCH"} else (75 if genre in {"PRODUCT_ANNOUNCEMENT", "COMPANY_ANNOUNCEMENT", "NEWS_EVENT"} else (45 if genre == "ANALYSIS" else 15))
        if len(e.primary_entities) >= 2: e.newsworthiness_score += 5
        if len(set(e.publisher_ids or e.source_ids)) > 1: e.newsworthiness_score += 10
        if genre in {"INTERVIEW", "OPINION"}: e.newsworthiness_score *= .5
        vals = (e.topic_relevance, e.newsworthiness_score, e.source_quality, e.source_diversity, e.recency, e.coverage); ws = (weights.get("topic_relevance", .25), weights.get("newsworthiness", .30), weights.get("source_quality", .15), weights.get("source_diversity", .15), weights.get("recency", .10), weights.get("coverage", .05)); e.relevance_score = round(sum(w*v for w,v in zip(ws, vals)), 2)
    return sorted([e for e in events if e.categories != ["OTHER"] and e.content_genre not in {"EVENT_PROMOTION", "PROMOTION", "ROUNDUP", "BUYING_GUIDE", "HOW_TO", "REVIEW", "DEAL_COUPON", "INTERVIEW", "OPINION"}], key=lambda e: e.relevance_score, reverse=True)

