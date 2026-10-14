"""Breaking-news push: a story many outlets start covering at once, sent to users who opted in.

An event (articles the clustering grouped under one ``event_id``) is breaking when:

- at least BREAKING_MIN_SOURCES distinct sources published it within the last
  BREAKING_WINDOW_MINUTES, and no article of the event is older than that window (a new story,
  not an old one resurfacing);
- its lead article is news, not a deal, guide, review, roundup, how-to or opinion piece.

A user receives it when ``notifications_enabled`` and ``breaking_news_enabled`` are on, the event
matches their topics and country scope, it is outside their quiet hours (local time), they got
fewer than BREAKING_MAX_PER_DAY breaking pushes in the last 24 hours and none in the last
BREAKING_MIN_GAP_MINUTES. Each event reaches each device at most once; a push still undelivered
BREAKING_MAX_DELAY_MINUTES after detection is cancelled instead of sent late.
"""
import json
import os
import re
import time
import uuid
from datetime import timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from newzi_engine.topic_registry import taxonomy

from .timeutil import iso, parse, utc_now

NOTIFICATION_TYPE = "BREAKING_NEWS"
# The engine genre classifier only knows English titles.
_NOT_NEWS_PT = re.compile(r"^(como|veja como|por que|entenda|guia|review|análise|opinião|teste)\b|\b(melhores|ofertas?|promoç(ão|ões)|cupons?|desconto)\b",
                          re.IGNORECASE)


def _env_int(name, default):
    return int(os.getenv(name, str(default)))


def _quiet_hours(value):
    """``22-7`` -> (22, 7); an empty value disables quiet hours."""
    if not value or not value.strip():
        return None
    start, end = (int(part) for part in value.split("-", 1))
    return start % 24, end % 24


def in_quiet_hours(hour, quiet):
    if not quiet or quiet[0] == quiet[1]:
        return False
    start, end = quiet
    return start <= hour < end if start < end else hour >= start or hour < end


def is_news(title, description="", url=""):
    if _NOT_NEWS_PT.search(title or ""):
        return False
    from newzi_engine.editorial.genre import EXCLUDED, classify_genre
    article = classify_genre(SimpleNamespace(title=title or "", description=description or "", url=url or "", source_tags=[]))
    return article.content_genre not in EXCLUDED | {"ANALYSIS"}


class BreakingNewsService:
    def __init__(self, repo):
        self.repo = repo
        self.enabled = os.getenv("BREAKING_NEWS_ENABLED", "true").lower() not in ("0", "false", "no")
        self.min_sources = max(2, _env_int("BREAKING_MIN_SOURCES", 3))
        self.window = timedelta(minutes=max(10, _env_int("BREAKING_WINDOW_MINUTES", 180)))
        self.max_per_day = max(1, _env_int("BREAKING_MAX_PER_DAY", 2))
        self.min_gap = timedelta(minutes=max(0, _env_int("BREAKING_MIN_GAP_MINUTES", 180)))
        self.max_delay = timedelta(minutes=max(5, _env_int("BREAKING_MAX_DELAY_MINUTES", 60)))
        self.quiet = _quiet_hours(os.getenv("BREAKING_QUIET_HOURS", "22-7"))
        self.check_interval = max(0, _env_int("BREAKING_CHECK_SECONDS", 300))
        self._last_check = None

    # Detection
    def detect(self, now=None):
        """Breaking events at ``now``: dicts with the lead article, source count and topics."""
        now = now or utc_now()
        lower, upper = iso(now - self.window), iso(now + timedelta(minutes=10))
        candidates = self.repo.db.execute(
            """SELECT event_id FROM indexed_content WHERE event_id IS NOT NULL AND event_id<>'' AND published_at>=? AND published_at<=?
               GROUP BY event_id HAVING COUNT(DISTINCT source_id)>=?""", (lower, upper, self.min_sources)).fetchall()
        events = []
        for candidate in candidates:
            event_id = candidate["event_id"]
            articles = self.repo.db.execute(
                """SELECT id,title,description,url,source_name,source_id,source_country,source_language,published_at,quality_score
                   FROM indexed_content WHERE event_id=? AND published_at IS NOT NULL ORDER BY published_at,id""", (event_id,)).fetchall()
            if not articles or articles[0]["published_at"] < lower:
                continue  # the story started before the window: an old event gaining coverage
            lead = sorted(articles, key=lambda row: (row["source_language"] != "pt-BR" and row["source_language"] != "pt",
                                                     -(row["quality_score"] or 0), row["published_at"]))[0]
            if not is_news(lead["title"], lead["description"], lead["url"]):
                continue
            marks = ",".join("?" for _ in articles)
            topics = {row[0] for row in self.repo.db.execute(
                f"SELECT DISTINCT taxonomy_id FROM content_taxonomy WHERE content_id IN ({marks})", tuple(row["id"] for row in articles))}
            events.append({"event_id": event_id, "lead": dict(lead), "detected_at": iso(now),
                           "source_count": len({row["source_id"] for row in articles}),
                           "countries": {row["source_country"] for row in articles}, "topics": topics})
        return events

    # Audience
    def _subscribers(self):
        rows = self.repo.db.execute(
            """SELECT p.* FROM user_preferences p JOIN users u ON u.id=p.user_id
               JOIN notification_settings s ON s.user_id=p.user_id
               WHERE u.status='ACTIVE' AND s.notifications_enabled=1 AND s.breaking_news_enabled=1
               AND EXISTS (SELECT 1 FROM push_devices d WHERE d.user_id=p.user_id AND d.enabled=1 AND d.invalidated_at IS NULL)""").fetchall()
        return [(row["user_id"], self.repo._preferences_from_row(row)) for row in rows]

    @staticmethod
    def matches(prefs, event):
        scope = prefs.get("country_scope")
        if scope == "LOCAL" and "BR" not in event["countries"]:
            return False
        if scope == "GLOBAL" and not (event["countries"] - {"BR"}):
            return False
        if prefs.get("content_scope") == "all":
            return True
        registry = taxonomy()
        selected = set(prefs.get("topics") or [])
        interests = selected | {child for parent in selected for child in registry.descendants(parent)}
        return bool(interests & event["topics"])

    def _within_limits(self, user_id, prefs, now):
        try:
            local_hour = now.astimezone(ZoneInfo(prefs.get("timezone") or "UTC")).hour
        except Exception:
            local_hour = now.hour
        if in_quiet_hours(local_hour, self.quiet):
            return False
        sent = self.repo.db.execute(
            """SELECT COUNT(DISTINCT delivery_id) AS events,MAX(created_at) AS latest FROM notification_jobs
               WHERE user_id=? AND notification_type=? AND created_at>=? AND status<>'CANCELLED'""",
            (user_id, NOTIFICATION_TYPE, iso(now - timedelta(hours=24)))).fetchone()
        if sent["events"] >= self.max_per_day:
            return False
        return not (sent["latest"] and parse(sent["latest"]) > now - self.min_gap)

    @staticmethod
    def payload(event, language):
        lead = event["lead"]; others = event["source_count"] - 1
        headline = (lead["title"] or "").strip()
        title = headline if len(headline) <= 110 else headline[:107].rstrip() + "..."
        if language and language.lower().startswith("en"):
            body = f"{lead['source_name']} and {others} other outlets are covering this story."
        else:
            body = f"{lead['source_name']} e mais {others} veículos estão cobrindo esta notícia."
        return {"title": title, "body": body,
                "data": {"type": NOTIFICATION_TYPE, "event_id": event["event_id"], "story_id": lead["id"], "url": lead["url"]}}

    def enqueue(self, events, now=None):
        now = now or utc_now(); created = 0; users = set()
        subscribers = self._subscribers() if events else []
        for event in events:
            delivery_id = "breaking_" + event["event_id"]
            for user_id, prefs in subscribers:
                if not self.matches(prefs, event):
                    continue
                already = self.repo.db.execute("SELECT 1 FROM notification_jobs WHERE user_id=? AND delivery_id=? LIMIT 1",
                                               (user_id, delivery_id)).fetchone()
                if already or not self._within_limits(user_id, prefs, now):
                    continue
                payload = json.dumps(self.payload(event, prefs.get("language")), ensure_ascii=False)
                devices = self.repo.db.execute("SELECT id FROM push_devices WHERE user_id=? AND enabled=1 AND invalidated_at IS NULL",
                                               (user_id,)).fetchall()
                for device in devices:
                    cursor = self.repo.db.execute(
                        """INSERT INTO notification_jobs(id,user_id,delivery_id,device_id,notification_type,scheduled_for,status,attempt_count,
                           max_attempts,next_attempt_at,provider_message_id,last_error,created_at,updated_at,payload_json)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING""",
                        ("notification_" + uuid.uuid4().hex, user_id, delivery_id, device["id"], NOTIFICATION_TYPE, iso(now), "PENDING",
                         0, 3, None, None, None, iso(now), iso(now), payload))
                    created += cursor.rowcount
                users.add(user_id)
                # Commit per user so the next user's limits see these jobs even if a later insert fails.
                self.repo.db.commit()
        return {"breaking_jobs_created": created, "breaking_users": len(users)}

    def run_once(self, now=None, force=False):
        if not self.enabled:
            return {"status": "DISABLED"}
        if not force and self._last_check is not None and time.monotonic() - self._last_check < self.check_interval:
            return {"status": "NOT_DUE"}
        self._last_check = time.monotonic()
        if not self.repo.db.execute("SELECT 1 FROM notification_settings WHERE notifications_enabled=1 AND breaking_news_enabled=1 LIMIT 1").fetchone():
            return {"status": "NO_SUBSCRIBERS"}
        events = self.detect(now)
        result = self.enqueue(events, now)
        self.repo.db.commit()
        return {"status": "CHECKED", "events": len(events), **result}
