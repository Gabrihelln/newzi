import re
from ..utils.text import normalize_title, tokens

GENERIC = {"ai", "agents", "agent", "technology", "tech", "software", "company", "product", "news", "new", "update", "updates", "features", "service", "platform", "model", "launch", "launches", "available", "latest", "major", "startup", "solution", "finds", "says", "wants", "states", "cameras", "dollar", "gamble", "stake", "trillion", "what", "whats", "or", "and"}
KNOWN = {"apple", "microsoft", "google", "openai", "anthropic", "amazon", "aws", "meta", "meta one", "samsung", "nvidia", "perplexity", "volvo", "xc60", "xc90", "iphone 18", "iphone 18 pro", "apple pencil", "siri", "gpt-6 astra", "gpt 6 astra", "agents api", "euclyd", "john deere", "home depot", "surfshark", "lg", "sam altman", "techcrunch disrupt", "ios 27", "ipad os 27", "child safety", "profound", "flock"}
PRODUCTS = {"meta one", "gpt-6 astra", "gpt 6 astra", "agents api", "iphone 18", "iphone 18 pro", "apple pencil", "siri", "xc60", "xc90", "ios 27", "ipad os 27"}
ACTIONS = {"launch", "launches", "launched", "introduce", "introducing", "announces", "announced", "release", "releases", "released", "funding", "raises", "acquire", "acquisition", "backs", "unveils", "unveiled", "files", "bans", "approves", "research", "study"}
ENTITY_STOP = GENERIC | ACTIONS | {"series", "round", "million", "billion", "months", "month", "year", "years", "before", "after", "with", "from", "into", "the", "this", "that", "how", "why", "top", "newest"}

def _proper_candidates(title):
    words=re.findall(r"\b[A-Z][A-Za-z0-9-]{2,}\b", title)
    return {w.casefold() for i,w in enumerate(words) if i > 0 and w.casefold() not in ENTITY_STOP and not w.isdigit()}

def fingerprint(article):
    raw = normalize_title(f"{article.title} {article.description}")
    numeric_raw = f"{article.title} {article.description}".replace("â€”", " ").replace("â€“", " ").casefold()
    entities = {x for x in KNOWN if re.search(r"\b"+re.escape(x)+r"\b", raw)} | _proper_candidates(article.title)
    entities = {x for x in entities if x not in ENTITY_STOP and not re.fullmatch(r"\d+", x)}
    product_entities = entities & PRODUCTS
    distinctive = {t for t in tokens(article.title) if t not in ENTITY_STOP and len(t) >= 4 and not t.isdigit()}
    numbers = re.findall(r"\$?\d+(?:[.,]\d+)?\s*(?:million|billion|m|bn|%)?", numeric_raw)
    amounts = [x for x in numbers if "$" in x or any(u in x for u in ("million", "billion", "m", "bn"))]
    dates = re.findall(r"\b(?:20\d{2}|\d+\s+(?:days?|weeks?|months?|years?))\b", raw)
    action_terms = sorted(set(ACTIONS) & set(tokens(article.title)))
    return {"primary_entities": sorted(entities), "primary_subject": sorted(product_entities or entities)[:5], "product_entities": sorted(product_entities), "action_terms": action_terms, "numbers": numbers, "amounts": amounts, "dates": dates, "distinctive_tokens": sorted(distinctive), "event_terms": sorted(set(tokens(article.title)) & {"funding", "ipo", "acquisition", "launch", "release", "research", "regulation", "lawsuit", "ban"}), "content_genre": article.content_genre}

def apply_fingerprint(article):
    article.fingerprint = fingerprint(article)
    return article

