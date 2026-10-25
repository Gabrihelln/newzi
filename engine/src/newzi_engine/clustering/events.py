import hashlib
import logging
import time
from collections import defaultdict
from .similarity import can_reach_merge_or_audit_floor, mark_specific_terms, prepare_similarity_features, signal_pair, should_merge
from ..models import NewsEvent
from ..utils.text import tokens
from ..editorial.fingerprint import apply_fingerprint

# Bump when merge rules change: the product index re-clusters its recent stories once.
CLUSTER_VERSION = "anchor-specific-v2"


def _fits_anchor(signals):
    """A joining story must still be about the event's first story, not only its closest member.

    Without this, single-link merging chains unrelated stories through shared brands
    (Gemini launch -> Pixel leak -> Moto Watch -> ...).
    """
    return not signals["conflict"] and (signals["specific_shared"] >= 2 or signals["title_similarity"] >= .25)


def _representative(articles, source_priorities=None):
    priorities = source_priorities or {}
    return sorted(articles, key=lambda a: (a.language != "pt-BR", -priorities.get(a.source_id, 5), -len(a.title)))[0].title

def cluster_articles(articles, settings, sources=None, diagnostics=False, focus_ids=None, seed_events=None):
    """Group stories into events in one pass, oldest first.

    With ``focus_ids`` only those stories are placed; every other story keeps the event named in
    ``seed_events`` (or stays alone) and is only a candidate to join. A news cycle changes a few
    hundred stories of tens of thousands in the window, and re-deciding them all took hours.
    """
    cluster_started = time.perf_counter()
    cfg = settings.get("clustering", {}); window_hours = cfg.get("time_window_hours", 72); events = []; audit = {"merges": [], "near_misses": []}; priorities = {s["id"]: s.get("priority", 5) for s in (sources or [])}
    feature_started = time.perf_counter()
    for article in articles: apply_fingerprint(article)
    ordered = sorted(articles, key=lambda a: a.published_at or a.collected_at)
    features = mark_specific_terms([prepare_similarity_features(article) for article in ordered])
    feature_ms = (time.perf_counter() - feature_started) * 1000
    postings = defaultdict(list)
    article_events = {}
    article_by_index = {}
    anchors = {}  # id(event) -> index of the story that opened it
    comparisons = 0; candidate_pairs = 0; candidate_generation_ms = 0.0
    cheap_pruning_ms = 0.0; similarity_ms = 0.0; event_lookup_ms = 0.0
    event_mutation_ms = 0.0; feature_postings_ms = 0.0
    progress_every = max(1, int(cfg.get("progress_interval", 250)))
    def register(index, article, event):
        article_events[index] = event
        article_by_index[index] = article
        postings_started = time.perf_counter()
        for term in features[index]["candidate_terms"]:
            postings[term].append(index)
        return (time.perf_counter() - postings_started) * 1000

    def open_event(index, article, eid=None):
        eid = eid or hashlib.sha256((article.canonical_url or article.title).encode()).hexdigest()[:16]
        events.append(NewsEvent(eid, article.title, list(article.categories) or ["OTHER"], [article.article_id], [article.source_id], article.published_at or article.collected_at, article.published_at or article.collected_at, article.published_at, keywords=sorted(tokens(article.title)), articles=[article], cluster_confidence=0.0, publisher_ids=[article.publisher_id or article.source_id], primary_entities=article.fingerprint.get("primary_subject", []), content_genre=article.content_genre, fingerprint=article.fingerprint))
        anchors[id(events[-1])] = index
        return events[-1]

    def join(event, article, signals=None):
        event.articles.append(article); event.article_ids.append(article.article_id); event.source_ids = sorted(set(event.source_ids + [article.source_id])); event.publisher_ids = sorted(set(event.publisher_ids + [article.publisher_id or article.source_id])); event.first_seen_at = min(event.first_seen_at, article.published_at or article.collected_at); event.last_seen_at = max(event.last_seen_at, article.published_at or article.collected_at); event.categories = sorted({c for c in event.categories + article.categories if c != "OTHER"}) or ["OTHER"]; event.keywords = sorted(set(event.keywords + list(tokens(article.title)))); event.primary_entities = sorted(set(event.primary_entities + article.fingerprint.get("primary_subject", []))); event.representative_title = _representative(event.articles, priorities)
        if signals:
            event.cluster_confidence = round(max(event.cluster_confidence, signals["confidence"]), 2); event.merge_audit.append({"article_a": event.articles[0].title, "article_b": article.title, "genre": article.content_genre, "fingerprint_a": event.articles[0].fingerprint, "fingerprint_b": article.fingerprint, **signals}); audit["merges"].append(event.merge_audit[-1])

    placing = list(enumerate(ordered))
    if focus_ids is not None:
        # Settled stories go in first, as they stand, so a changed story can join one published after it.
        seeded = {}; seeds = seed_events or {}
        for index, article in placing:
            if article.article_id in focus_ids: continue
            seed = seeds.get(article.article_id)
            if seed and seed in seeded:
                event = seeded[seed]; join(event, article)
            else:
                event = open_event(index, article, seed)
                if seed: seeded[seed] = event
            feature_postings_ms += register(index, article, event)
        placing = [(index, article) for index, article in placing if article.article_id in focus_ids]
    for position, (index, article) in enumerate(placing):
        if position and position % progress_every == 0:
            logging.info("[CLUSTER] progress=%s/%s events=%s comparisons=%s", position, len(placing), len(events), comparisons)
        current_features = features[index]
        candidate_started = time.perf_counter()
        candidate_indices = set()
        for term in current_features["candidate_terms"]:
            candidate_indices.update(postings.get(term, ()))
        candidate_generation_ms += (time.perf_counter() - candidate_started) * 1000
        candidate_pairs += len(candidate_indices)
        best = None; best_signals = None; best_index = None
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
                best, best_signals, best_index = existing_event, signals, existing_index
            event_lookup_ms += (time.perf_counter() - event_lookup_started) * 1000
        mutation_started = time.perf_counter()
        merge = bool(best) and should_merge(best_signals)
        if merge and best_index != anchors[id(best)]:
            anchor_index = anchors[id(best)]
            merge = _fits_anchor(signal_pair(article, ordered[anchor_index], window_hours, features_a=current_features, features_b=features[anchor_index]))
        if merge:
            join(best, article, best_signals)
        else:
            if best_signals and best_signals["confidence"] >= 35: audit["near_misses"].append({"article_a": best.articles[0].title if best else "", "article_b": article.title, **best_signals})
            best = open_event(index, article)
        event_mutation_ms += (time.perf_counter() - mutation_started) * 1000
        feature_postings_ms += register(index, article, best)
    audit["metrics"] = {
        "pair_comparisons": comparisons,
        "articles_placed": len(placing),
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

