import math, re
from collections import Counter
from ..utils.text import normalize_title, tokens
from ..editorial.fingerprint import fingerprint

GENERIC = {"new", "news", "update", "updates", "launch", "launches", "announces", "announced", "available", "latest", "major", "introducing", "inside", "first", "look", "technology", "tech", "company", "service", "features", "model"}
KNOWN = {"meta", "meta one", "openai", "sam altman", "google", "apple", "microsoft", "amazon", "aws", "anthropic", "claude", "gemini", "gpt", "volvo", "xc60", "xc90", "john deere", "disrupt", "infrastructure lab", "data centers", "child safety", "software platforms"}

def cosine(a, b):
    if not a or not b: return 0.0
    ca, cb = Counter(a), Counter(b); dot = sum(ca[k] * cb[k] for k in ca.keys() & cb.keys())
    return dot / (math.sqrt(sum(v*v for v in ca.values())) * math.sqrt(sum(v*v for v in cb.values())))

def title_similarity(a, b): return cosine(tokens(a.title), tokens(b.title))

def distinctive_tokens(article):
    raw = normalize_title(f"{article.title} {article.description}")
    result = {t for t in tokens(article.title) if t not in GENERIC and len(t) >= 4}
    for entity in KNOWN:
        if entity in raw: result.add(entity)
    result.update(re.findall(r"\b\d+[a-z0-9-]*\b", raw))
    return result

def entity_overlap(a, b):
    ea, eb = distinctive_tokens(a), distinctive_tokens(b)
    if not ea or not eb: return 0.0
    return len(ea & eb) / max(1, min(len(ea), len(eb)))

def temporal_score(a, b, window_hours=72):
    if not a.published_at or not b.published_at: return .5
    hours = abs((a.published_at - b.published_at).total_seconds()) / 3600
    return max(0.0, 1.0 - hours / window_hours)

def prepare_similarity_features(article):
    """Cache normalized values used by every pair comparison during clustering."""
    fp = article.fingerprint or fingerprint(article)
    title_terms = frozenset(tokens(article.title))
    distinctive = frozenset(distinctive_tokens(article))
    primary_subject = frozenset(fp.get("primary_subject", []))
    return {
        "fingerprint": fp,
        "title_terms": title_terms,
        "distinctive": distinctive,
        "subjects": primary_subject | distinctive,
        "entities": frozenset(fp.get("primary_entities", [])),
        "products": frozenset(fp.get("product_entities", [])),
        "actions": frozenset(fp.get("action_terms", [])),
        # Any pair that can exceed the audit/merge confidence floor must share
        # title, distinctive, subject, or entity evidence.
        "candidate_terms": title_terms | distinctive | primary_subject | frozenset(fp.get("primary_entities", [])) | frozenset(fp.get("product_entities", [])),
    }


def can_reach_merge_or_audit_floor(a, b, features_a, features_b):
    """Cheap upper bound; false means the pair cannot merge or be audited."""
    title_a, title_b = features_a["title_terms"], features_b["title_terms"]
    shared_title = len(title_a & title_b)
    title_similarity_score = shared_title / math.sqrt(max(1, len(title_a)) * max(1, len(title_b)))
    subjects_a, subjects_b = features_a["subjects"], features_b["subjects"]
    shared_subjects = len(subjects_a & subjects_b)
    subject_overlap = shared_subjects / max(1, min(len(subjects_a), len(subjects_b)))
    shared_entities = bool(features_a["entities"] & features_b["entities"] or features_a["products"] & features_b["products"])
    if a.source_id == b.source_id and title_similarity_score >= .72 and subject_overlap >= .45:
        # Same-source merges deliberately do not use the cross-source confidence
        # floor or temporal cutoff.
        return True
    upper_bound = .30 * title_similarity_score + .30 * subject_overlap + .15 + .15 * shared_entities + .10 * (a.source_id != b.source_id)
    return upper_bound >= .35


def signal_pair(a, b, window_hours=72, *, features_a=None, features_b=None):
    features_a = features_a or prepare_similarity_features(a)
    features_b = features_b or prepare_similarity_features(b)
    fa, fb = features_a["fingerprint"], features_b["fingerprint"]
    da, db = features_a["subjects"], features_b["subjects"]
    title_terms_a, title_terms_b = features_a["title_terms"], features_b["title_terms"]
    shared_title_terms = title_terms_a & title_terms_b
    overlap = len(da & db) / max(1, min(len(da), len(db)))
    raw_overlap = len(shared_title_terms) / max(1, min(len(title_terms_a), len(title_terms_b)))
    title = len(shared_title_terms) / math.sqrt(max(1, len(title_terms_a)) * max(1, len(title_terms_b)))
    temporal = temporal_score(a, b, window_hours)
    same_source = a.source_id == b.source_id
    shared_entities = features_a["entities"] & features_b["entities"]
    shared_products = features_a["products"] & features_b["products"]
    shared_actions = features_a["actions"] & features_b["actions"]
    distinctive_a, distinctive_b = features_a["distinctive"], features_b["distinctive"]
    distinctive_overlap_score = len(distinctive_a & distinctive_b) / max(1, min(len(distinctive_a), len(distinctive_b))) if distinctive_a and distinctive_b else 0.0
    conflicts = (not shared_entities and not shared_products and bool(da and db)) or (("child safety" in da and "software platforms" in db) or ("software platforms" in da and "child safety" in db))
    genre_conflict = a.content_genre in {"PROMOTION", "EVENT_PROMOTION", "ROUNDUP", "DEAL_COUPON", "BUYING_GUIDE"} or b.content_genre in {"PROMOTION", "EVENT_PROMOTION", "ROUNDUP", "DEAL_COUPON", "BUYING_GUIDE"}
    action_agreement = bool(shared_actions or a.content_genre == b.content_genre)
    if conflicts: overlap *= .1
    confidence = 100 * (.30 * title + .30 * overlap + .15 * temporal + .15 * bool(shared_entities or shared_products) + .10 * (0 if same_source else 1))
    if conflicts: confidence *= .25
    return {"title_similarity": round(title, 3), "token_overlap": round(raw_overlap, 3), "entity_overlap": round(distinctive_overlap_score, 3), "distinctive_overlap": round(overlap, 3), "temporal_score": round(temporal, 3), "same_source": same_source, "conflict": bool(conflicts), "genre_conflict": genre_conflict, "action_agreement": action_agreement, "shared_entities": sorted(shared_entities | shared_products), "confidence": round(confidence, 2)}

def should_merge(signals):
    if signals["conflict"] or signals["genre_conflict"] or not signals["action_agreement"]: return False
    if signals["same_source"]: return signals["title_similarity"] >= .72 and signals["distinctive_overlap"] >= .45
    return ((signals["entity_overlap"] >= .50 and signals["distinctive_overlap"] >= .40) or (signals["title_similarity"] >= .58 and signals["distinctive_overlap"] >= .30) or (signals["title_similarity"] >= .45 and signals["token_overlap"] >= .60 and signals["action_agreement"])) and signals["temporal_score"] > 0 and signals["confidence"] >= 35

