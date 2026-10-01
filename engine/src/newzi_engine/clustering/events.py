import hashlib
import logging
import time
from collections import defaultdict
from .similarity import can_reach_merge_or_audit_floor, prepare_similarity_features, signal_pair, should_merge
from ..models import NewsEvent
from ..utils.text import tokens
from ..editorial.fingerprint import apply_fingerprint

def _representative(articles, source_priorities=None):
    priorities = source_priorities or {}
    return sorted(articles, key=lambda a: (a.language != "pt-BR", -priorities.get(a.source_id, 5), -len(a.title)))[0].title

def cluster_articles(articles, settings, sources=None, diagnostics=False):
    cluster_started = time.perf_counter()
    cfg = settings.get("clustering", {}); window_hours = cfg.get("time_window_hours", 72); events = []; audit = {"merges": [], "near_misses": []}; priorities = {s["id"]: s.get("priority", 5) for s in (sources or [])}
    feature_started = time.perf_counter()
    for article in articles: apply_fingerprint(article)
    ordered = sorted(articles, key=lambda a: a.published_at or a.collected_at)
    features = [prepare_similarity_features(article) for article in ordered]
    feature_ms = (time.perf_counter() - feature_started) * 1000
    postings = defaultdict(list)
    article_events = {}
    article_by_index = {}
    comparisons = 0; candidate_pairs = 0; candidate_generation_ms = 0.0
    cheap_pruning_ms = 0.0; similarity_ms = 0.0; event_lookup_ms = 0.0
    event_mutation_ms = 0.0; feature_postings_ms = 0.0
    progress_every = max(1, int(cfg.get("progress_interval", 250)))
    for index, article in enumerate(ordered):
        if index and index % progress_every == 0:
            logging.info("[CLUSTER] progress=%s/%s events=%s comparisons=%s", index, len(ordered), len(events), comparisons)
        current_features = features[index]
        candidate_started = time.perf_counter()
        candidate_indices = set()
        for term in current_features["candidate_terms"]:
            candidate_indices.update(postings.get(term, ()))
        candidate_generation_ms += (time.perf_counter() - candidate_started) * 1000
        candidate_pairs += len(candidate_indices)
        best = None; best_signals = None
        # Pairs without shared title/subject/entity evidence cannot reach the
        # merge threshold or the near-miss audit threshold, so skip them safely.
        for existing_index in sorted(candidate_indices):
            existing = article_by_index[existing_index]
            cheap_started = time.perf_counter()
            if not can_reach_merge_or_audit_floor(article, existing, current_features, features[existing_index]):
                cheap_pruning_ms += (time.perf_counter() - cheap_started) * 1000
                continue
            cheap_pruning_ms += (time.perf_counter() - cheap_started) * 1000
            similarity_started = time.perf_counter()
            signals = signal_pair(article, existing, window_hours, features_a=current_features, features_b=features[existing_index])
            similarity_ms += (time.perf_counter() - similarity_started) * 1000
            comparisons += 1
            event_lookup_started = time.perf_counter()
            existing_event = article_events[existing_index]
            if best_signals is None or signals["confidence"] > best_signals["confidence"]:
                best, best_signals = existing_event, signals
            event_lookup_ms += (time.perf_counter() - event_lookup_started) * 1000
        mutation_started = time.perf_counter()
        if best and should_merge(best_signals):
            best.articles.append(article); best.article_ids.append(article.article_id); best.source_ids = sorted(set(best.source_ids + [article.source_id])); best.publisher_ids = sorted(set(best.publisher_ids + [article.publisher_id or article.source_id])); best.last_seen_at = max(best.last_seen_at, article.published_at or article.collected_at); best.categories = sorted({c for c in best.categories + article.categories if c != "OTHER"}) or ["OTHER"]; best.keywords = sorted(set(best.keywords + list(tokens(article.title)))); best.primary_entities = sorted(set(best.primary_entities + article.fingerprint.get("primary_subject", []))); best.representative_title = _representative(best.articles, priorities); best.cluster_confidence = round(max(best.cluster_confidence, best_signals["confidence"]), 2); best.merge_audit.append({"article_a": best.articles[0].title, "article_b": article.title, "genre": article.content_genre, "fingerprint_a": best.articles[0].fingerprint, "fingerprint_b": article.fingerprint, **best_signals}); audit["merges"].append(best.merge_audit[-1])
        else:
            if best_signals and best_signals["confidence"] >= 35: audit["near_misses"].append({"article_a": best.articles[0].title if best else "", "article_b": article.title, **best_signals})
            eid = hashlib.sha256((article.canonical_url or article.title).encode()).hexdigest()[:16]
            events.append(NewsEvent(eid, article.title, list(article.categories) or ["OTHER"], [article.article_id], [article.source_id], article.published_at or article.collected_at, article.published_at or article.collected_at, article.published_at, keywords=sorted(tokens(article.title)), articles=[article], cluster_confidence=0.0, publisher_ids=[article.publisher_id or article.source_id], primary_entities=article.fingerprint.get("primary_subject", []), content_genre=article.content_genre, fingerprint=article.fingerprint))
            best = events[-1]
        event_mutation_ms += (time.perf_counter() - mutation_started) * 1000
        article_events[index] = best
        article_by_index[index] = article
        postings_started = time.perf_counter()
        for term in current_features["candidate_terms"]:
            postings[term].append(index)
        feature_postings_ms += (time.perf_counter() - postings_started) * 1000
    audit["metrics"] = {
        "pair_comparisons": comparisons,
        "candidate_pairs": candidate_pairs,
        "possible_pairs": len(ordered) * max(0, len(ordered) - 1) // 2,
        "pairs_skipped": len(ordered) * max(0, len(ordered) - 1) // 2 - comparisons,
        "timings_ms": {
            "feature_preparation": round(feature_ms, 2),
            "candidate_generation": round(candidate_generation_ms, 2),
            "cheap_pruning": round(cheap_pruning_ms, 2),
            "full_similarity": round(similarity_ms, 2),
            "event_lookup": round(event_lookup_ms, 2),
            "event_mutation": round(event_mutation_ms, 2),
            "posting_update": round(feature_postings_ms, 2),
            "total": round((time.perf_counter() - cluster_started) * 1000, 2),
        },
    }
    logging.info("[CLUSTER] completed articles=%s events=%s candidate_pairs=%s comparisons=%s possible_pairs=%s timings_ms=%s", len(ordered), len(events), candidate_pairs, comparisons, audit["metrics"]["possible_pairs"], audit["metrics"]["timings_ms"])
    return (events, audit) if diagnostics else events

