"""Breaking-news push: a story many outlets start covering at once, sent to users who opted in.

An event (articles the clustering grouped under one ``event_id``) is breaking when:

- at least BREAKING_MIN_SOURCES (5) distinct sources published it within the last
  BREAKING_WINDOW_MINUTES (90), and no article of the event is older than that window (many outlets
  at once, not an old story slowly gaining coverage);
- its lead article is news, not a deal, guide, review, roundup, how-to or opinion piece.

The push carries the lead headline as its title and a short summary of the story as its body
(``story_summary``); tapping it opens the story.

A user receives it when ``notifications_enabled`` and ``breaking_news_enabled`` are on, the event
matches their topics (a followed domain covers its subjects; "follow everything" covers all), country
scope and language (a Portuguese reader only gets stories with Portuguese coverage), and it is outside their quiet hours (local time). To keep it from becoming noise:

- at least BREAKING_MIN_GAP_MINUTES (45) pass between two breaking pushes to the same user. A story
  found during the gap waits; when the gap ends the strongest story still breaking (most sources) goes
  out, and stories that lost their momentum meanwhile (fell out of the window) are dropped;
- at most BREAKING_DAILY_LIMIT (5) a day per user (their local day). Past it, only a story covered by
  BREAKING_EXCEPTIONAL_SOURCES (10) outlets is still sent, after the gap like any other.

Each event, and the same story under a new event id or already sent as a team-news alert, reaches each
user at most once (``already_told``); a push still undelivered BREAKING_MAX_DELAY_MINUTES after detection
is cancelled instead of sent late.
"""
import html
import json
import os
import re
import time
import uuid
from datetime import timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from newzi_engine.topic_registry import taxonomy

from .timeutil import iso, parse, utc_now

NOTIFICATION_TYPE = "BREAKING_NEWS"
# News pushes that tell a story: one story reaches a person through at most one of them.
STORY_TYPES = ("BREAKING_NEWS", "TEAM_NEWS", "KEYWORD_ALERT", "STORY_UPDATE")
# The engine genre classifier only knows English titles.
_NOT_NEWS_PT = re.compile(r"^(como|veja como|por que|entenda|guia|review|análise|opinião|teste)\b|\b(melhores|ofertas?|promoç(ão|ões)|cupons?|desconto)\b",
                          re.IGNORECASE)


def _env_int(name, default):
    return int(os.getenv(name, str(default)))


def breaking_rules():
    """The rules people see next to the switch ("3 veículos ou mais", "Silêncio 22h–7h"), from the same settings the sender uses."""
    quiet = _quiet_hours(os.getenv("BREAKING_QUIET_HOURS", "22-7"))
    return {"min_sources": max(2, _env_int("BREAKING_MIN_SOURCES", 5)),
            "quiet_hours": {"start": quiet[0], "end": quiet[1]} if quiet and quiet[0] != quiet[1] else None}


SUMMARY_LIMIT = 160
_TAGS = re.compile(r"<[^>]+>")
# Feed boilerplate that is not part of the story ("The post X appeared first on Y", "Leia mais", "[…]").
_BOILERPLATE = re.compile(r"(the post .+ appeared first on .+$|\b(leia|saiba|veja) mais\b.*$|continue lendo.*$|\[(…|\.\.\.)\]\s*$)", re.IGNORECASE)


def _clean(text):
    text = html.unescape(_TAGS.sub(" ", str(text or "")))
    text = _BOILERPLATE.sub("", re.sub(r"\s+", " ", text)).strip(" -–—|")
    return text.strip()


def _fold(text):
    return re.sub(r"[^\w]+", " ", (text or "").lower()).strip()


def story_summary(title, descriptions, limit=SUMMARY_LIMIT):
    """A short summary of the story for the notification body, from the first useful article description.

    Skips descriptions that only repeat the headline, drops a repeated headline at the start, and cuts at a
    sentence end when one fits (otherwise at a word, with an ellipsis). ``None`` when no article has one.
    """
    headline = _fold(title)
    for raw in descriptions:
        text = _clean(raw)
        if title and text.lower().startswith(title.strip().lower()):
            text = text[len(title.strip()):].lstrip(" .:-–—")
        folded = _fold(text)
        if len(folded) < 30 or folded == headline or (headline and headline.startswith(folded)):
            continue
        if len(text) <= limit:
            return text
        cut = text[:limit + 1]
        sentence = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        if sentence >= limit * 0.55:
            return cut[:sentence + 1]
        return cut[:cut.rfind(" ")].rstrip(" ,;:-–—") + "…"
    return None


def already_told(repo, user_id, story_ids, headline, now):
    """True when a news push of the last 24 h already told this person the story: it carried one of the
    story's articles (``story_ids``, the event's members) or the same headline."""
    folded = _fold(headline)
    for row in repo.db.execute(
            f"""SELECT DISTINCT payload_json FROM notification_jobs WHERE user_id=? AND notification_type IN ({",".join("?" for _ in STORY_TYPES)})
                AND created_at>=? AND payload_json IS NOT NULL""", (user_id, *STORY_TYPES, iso(now - timedelta(hours=24)))):
        sent = json.loads(row["payload_json"])
        if sent["data"].get("story_id") in story_ids or (folded and _fold(sent.get("title")) == folded):
            return True
    return False


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
        self.min_sources = max(2, _env_int("BREAKING_MIN_SOURCES", 5))
        self.window = timedelta(minutes=max(10, _env_int("BREAKING_WINDOW_MINUTES", 90)))
        self.min_gap = timedelta(minutes=max(0, _env_int("BREAKING_MIN_GAP_MINUTES", 45)))
        self.daily_limit = max(1, _env_int("BREAKING_DAILY_LIMIT", 5))
        self.exceptional_sources = max(self.min_sources, _env_int("BREAKING_EXCEPTIONAL_SOURCES", 10))
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
                """SELECT id,title,description,url,image_url,source_name,source_id,source_country,source_language,published_at,quality_score
                   FROM indexed_content WHERE event_id=? AND published_at IS NOT NULL ORDER BY published_at,id""", (event_id,)).fetchall()
            if not articles or articles[0]["published_at"] < lower:
                continue  # the story started before the window: an old event gaining coverage
            lead = sorted(articles, key=lambda row: (not str(row["source_language"] or "").startswith("pt"),
                                                     -(row["quality_score"] or 0), row["published_at"]))[0]
            if not is_news(lead["title"], lead["description"], lead["url"]):
                continue
            marks = ",".join("?" for _ in articles)
            topics = {row[0] for row in self.repo.db.execute(
                f"SELECT DISTINCT taxonomy_id FROM content_taxonomy WHERE content_id IN ({marks})", tuple(row["id"] for row in articles))}
            # The other articles feed the notification summary when the lead has no usable description.
            ranked = sorted(articles, key=lambda row: (not str(row["source_language"] or "").startswith("pt"), -(row["quality_score"] or 0)))
            events.append({"event_id": event_id, "lead": dict(lead), "detected_at": iso(now), "articles": [dict(row) for row in ranked],
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
        from .content import event_in_scope, event_readable
        if not event_in_scope(event["articles"], prefs.get("country_scope")) or not event_readable(event["articles"], prefs.get("language") or "pt-BR"):
            return False
        if prefs.get("content_scope") == "all":
            return True
        registry = taxonomy()
        selected = set(prefs.get("topics") or [])
        interests = selected | {child for parent in selected for child in registry.descendants(parent)}
        return bool(interests & event["topics"])

    def _awake(self, prefs, now):
        """Outside the user's quiet hours, in their own time zone."""
        try:
            local_hour = now.astimezone(ZoneInfo(prefs.get("timezone") or "UTC")).hour
        except Exception:
            local_hour = now.hour
        return not in_quiet_hours(local_hour, self.quiet)

    @staticmethod
    def _local_midnight(prefs, now):
        try:
            local = now.astimezone(ZoneInfo(prefs.get("timezone") or "UTC"))
        except Exception:
            local = now.astimezone(timezone.utc)
        return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

    def _paced(self, user_id, prefs, event, now):
        """Outside the gap since the last breaking push and under today's limit (an exceptional story skips the limit)."""
        today = self._local_midnight(prefs, now)
        sent = [parse(row[0]) for row in self.repo.db.execute(
            """SELECT MIN(created_at) FROM notification_jobs WHERE user_id=? AND notification_type=? AND status<>'CANCELLED'
               AND created_at>=? GROUP BY delivery_id""", (user_id, NOTIFICATION_TYPE, iso(min(now - self.min_gap, today))))]
        if any(moment > now - self.min_gap for moment in sent):
            return False
        return event["source_count"] >= self.exceptional_sources or sum(moment >= today for moment in sent) < self.daily_limit

    def _already_told(self, user_id, event, now):
        """The same story under another event id (re-clustering, a second wave of coverage) or already sent as team news is not news twice."""
        story_ids = {row["id"] for row in event.get("articles", [])} | {event["lead"]["id"]}
        return already_told(self.repo, user_id, story_ids, event["lead"]["title"], now)

    @staticmethod
    def payload(event, language):
        """Headline as the title and a short summary of the story as the body; a tap opens the story."""
        lead = event["lead"]; english = bool(language and language.lower().startswith("en"))
        headline = re.sub(r"\s+", " ", lead["title"] or "").strip()
        title = headline if len(headline) <= 110 else headline[:107].rstrip() + "…"
        others = [row["description"] for row in event.get("articles", []) if row["id"] != lead["id"]]
        body = story_summary(headline, [lead.get("description"), *others]) or (
            "Tap to read the full story on Newzi." if english else "Toque para ler a matéria completa no Newzi.")
        data = {"type": NOTIFICATION_TYPE, "event_id": event["event_id"], "story_id": lead["id"], "url": lead["url"]}
        image = lead.get("image_url")
        if image and str(image).startswith("https://"):
            data["image"] = image
        return {"title": title, "body": body, "data": data}

    def enqueue(self, events, now=None):
        now = now or utc_now(); created = 0; users = set()
        subscribers = self._subscribers() if events else []
        # Strongest first: when the gap lets only one story through, it is the one most outlets cover.
        for event in sorted(events, key=lambda item: -item["source_count"]):
            delivery_id = "breaking_" + event["event_id"]
            for user_id, prefs in subscribers:
                if not self.matches(prefs, event):
                    continue
                already = self.repo.db.execute("SELECT 1 FROM notification_jobs WHERE user_id=? AND delivery_id=? LIMIT 1",
                                               (user_id, delivery_id)).fetchone()
                if (already or self._already_told(user_id, event, now) or not self._awake(prefs, now)
                        or not self._paced(user_id, prefs, event, now)):
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
