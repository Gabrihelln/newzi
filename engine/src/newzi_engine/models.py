from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

@dataclass
class Article:
    article_id: str
    source_id: str
    source_name: str
    title: str
    description: str
    url: str
    canonical_url: str
    published_at: datetime | None
    collected_at: datetime
    language: str = "en"
    source_tags: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    source_type: str = "JOURNALISM"
    author: str | None = None
    publisher_id: str = ""
    content_genre: str = "OTHER"
    fingerprint: dict = field(default_factory=dict)
    image_url: str | None = None
    image_source: str | None = None
    image_checked_at: str | None = None

@dataclass
class NewsEvent:
    event_id: str
    representative_title: str
    categories: list[str]
    article_ids: list[str]
    source_ids: list[str]
    first_seen_at: datetime
    last_seen_at: datetime
    published_at: datetime | None
    relevance_score: float = 0.0
    keywords: list[str] = field(default_factory=list)
    articles: list[Article] = field(default_factory=list)
    cluster_confidence: float = 0.0
    topic_relevance: float = 0.0
    source_quality: float = 0.0
    source_diversity: float = 0.0
    recency: float = 0.0
    coverage: float = 0.0
    merge_audit: list[dict] = field(default_factory=list)
    publisher_ids: list[str] = field(default_factory=list)
    primary_entities: list[str] = field(default_factory=list)
    content_genre: str = "OTHER"
    fingerprint: dict = field(default_factory=dict)
    newsworthiness_score: float = 0.0

def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if dt else None

def article_from_row(row: Any) -> Article:
    keys = row.keys() if hasattr(row, "keys") else ()
    return Article(row["article_id"], row["source_id"], row["source_name"], row["title"], row["description"], row["url"], row["canonical_url"], datetime.fromisoformat(row["published_at"].replace("Z", "+00:00")) if row["published_at"] else None, datetime.fromisoformat(row["collected_at"].replace("Z", "+00:00")), row["language"], row["categories"].split(",") if row["categories"] else [], [], "JOURNALISM", image_url=row["image_url"] if "image_url" in keys else None, image_source=row["image_source"] if "image_source" in keys else None, image_checked_at=row["image_checked_at"] if "image_checked_at" in keys else None)

