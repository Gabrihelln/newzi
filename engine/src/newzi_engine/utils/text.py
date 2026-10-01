import hashlib
import html
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid", "mc_cid", "mc_eid"}
STOPWORDS = set("a an and are as at be by for from has in is it its of on or that the their this to was were with new news says about after before into over under via how why what when where will".split())

def clean_text(value: str | None) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def normalize_title(value: str) -> str:
    value = clean_text(value)
    value = value.replace("Ã¢â‚¬â€", " ").replace("Ã¢â‚¬â€œ", " ").replace("Ã¢â‚¬â„¢", " ").replace("Ã¢â‚¬Å“", " ").replace("Ã¢â‚¬Â", " ")
    value = re.sub(r"[\u2010-\u2015\u2018\u2019\u201c\u201d]", " ", value).casefold()
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9\s]", " ", value).strip().replace("  ", " ")

def canonicalize_url(url: str) -> str:
    parts = urlsplit((url or "").strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in TRACKING]
    path = re.sub(r"/+$", "", parts.path) or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))

def article_id(source_id: str, canonical_url: str, title: str) -> str:
    key = canonical_url or f"{source_id}:{normalize_title(title)}"
    return hashlib.sha256(key.encode()).hexdigest()[:24]

def tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", normalize_title(text).replace(" ", " ")) if t not in STOPWORDS}

