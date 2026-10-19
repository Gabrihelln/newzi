"""Personal alerts (Premium): keywords and followed stories.

- Keyword alerts: a person lists words or names (a company, a politician, a city, a stock); a new article whose
  headline names one of them is pushed (KEYWORD_ALERT). At most KEYWORD_ALERTS_PER_DAY a day per person and
  KEYWORD_ALERTS_PER_KEYWORD per keyword, never during quiet hours, and a story already told by another push
  (breaking news, team news, another keyword) is not told again.
- Followed stories ("Me avise quando essa história tiver novidade"): a new article in the story's event, from
  another outlet's coverage published after the last update, is pushed (STORY_UPDATE), at most once every
  STORY_UPDATE_GAP_HOURS per story. A story is followed for FOLLOW_DAYS days.

Run with the ``breaking`` worker role every ALERTS_CHECK_SECONDS. Only articles first seen since the previous check
are read, so a deploy or a new keyword never replays old news.
"""
import json
import os
import re
import time
import unicodedata
import uuid
from datetime import timedelta

from .notifications import NotificationService, wants
from .timeutil import iso, parse, utc_now

KEYWORD_ALERTS_PER_DAY = int(os.getenv("KEYWORD_ALERTS_PER_DAY", "10"))
KEYWORD_ALERTS_PER_KEYWORD = int(os.getenv("KEYWORD_ALERTS_PER_KEYWORD", "3"))
STORY_UPDATE_GAP = timedelta(hours=float(os.getenv("STORY_UPDATE_GAP_HOURS", "2")))
FOLLOW_DAYS = int(os.getenv("STORY_FOLLOW_DAYS", "7"))
CHECK_SECONDS = int(os.getenv("ALERTS_CHECK_SECONDS", "300"))
STATE_KEY = "alerts_checked_at"
MAX_KEYWORD = 40


def fold(value):
    return "".join(ch for ch in unicodedata.normalize("NFD", (value or "").casefold()) if unicodedata.category(ch) != "Mn")


def keyword_pattern(keyword):
    return re.compile(r"(?<![\w])" + re.escape(fold(keyword)) + r"(?![\w])")


def _clean_keyword(value):
    keyword = " ".join(str(value or "").split()).strip(" \"'“”")
    if len(keyword) < 2:
        raise ValueError("the keyword needs at least 2 characters")
    if len(keyword) > MAX_KEYWORD:
        raise ValueError(f"the keyword has at most {MAX_KEYWORD} characters")
    return keyword


# ------------------------------------------------------------------ keywords (API)
def list_keywords(repo, uid):
    return [{"id": row["id"], "keyword": row["keyword"], "created_at": row["created_at"]}
            for row in repo.db.execute("SELECT * FROM keyword_alerts WHERE user_id=? ORDER BY created_at", (uid,))]


def add_keyword(repo, uid, data):
    from .product_backend import ApiError
    from .subscriptions import PremiumRequired, limit, require
    require(repo, uid, "keyword_alerts")
    keyword = _clean_keyword((data or {}).get("keyword"))
    existing = list_keywords(repo, uid)
    if any(fold(item["keyword"]) == fold(keyword) for item in existing):
        raise ApiError("KEYWORD_EXISTS", "this keyword is already on your list", 409)
    if len(existing) >= limit(repo, uid, "keyword_alerts"):
        raise PremiumRequired("keyword_alerts", "keyword limit reached")
    repo.db.execute("INSERT INTO keyword_alerts(id,user_id,keyword,created_at) VALUES(?,?,?,?)", ("keyword_" + uuid.uuid4().hex, uid, keyword, iso(utc_now())))
    repo.db.commit()
    return {"items": list_keywords(repo, uid)}


def remove_keyword(repo, uid, keyword_id):
    repo.db.execute("DELETE FROM keyword_alerts WHERE id=? AND user_id=?", (keyword_id, uid))
    repo.db.commit()
    return {"items": list_keywords(repo, uid)}


# ------------------------------------------------------------------ followed stories (API)
def follow_story(repo, uid, story_id, following=True):
    from .product_backend import ApiError, not_found
    from .subscriptions import PremiumRequired, limit, require
    if not following:
        repo.db.execute("DELETE FROM followed_stories WHERE user_id=? AND story_id=?", (uid, story_id))
        repo.db.commit()
        return {"story_id": story_id, "following": False}
    require(repo, uid, "story_follow")
    article = repo.db.execute("SELECT id,title,event_id FROM indexed_content WHERE id=?", (story_id,)).fetchone()
    if not article:
        raise not_found("story not found")
    now = utc_now()
    repo.db.execute("DELETE FROM followed_stories WHERE expires_at<?", (iso(now),))
    count = repo.db.execute("SELECT COUNT(*) FROM followed_stories WHERE user_id=? AND story_id<>?", (uid, story_id)).fetchone()[0]
    if count >= limit(repo, uid, "followed_stories"):
        raise PremiumRequired("story_follow", "followed stories limit reached")
    if not article["title"]:
        raise ApiError("VALIDATION_ERROR", "story without headline", 400)
    repo.db.execute("""INSERT INTO followed_stories(user_id,story_id,event_id,headline,created_at,last_update_at,last_notified_at,expires_at)
        VALUES(?,?,?,?,?,?,NULL,?) ON CONFLICT(user_id,story_id) DO UPDATE SET expires_at=excluded.expires_at""",
        (uid, story_id, article["event_id"], article["title"], iso(now), iso(now), iso(now + timedelta(days=FOLLOW_DAYS))))
    repo.db.commit()
    return {"story_id": story_id, "following": True, "until": iso(now + timedelta(days=FOLLOW_DAYS))}


def followed_stories(repo, uid):
    now = iso(utc_now())
    return [{"story_id": row["story_id"], "headline": row["headline"], "until": row["expires_at"], "last_update_at": row["last_update_at"]}
            for row in repo.db.execute("SELECT * FROM followed_stories WHERE user_id=? AND expires_at>=? ORDER BY created_at DESC", (uid, now))]


def is_following(repo, uid, story_id):
    return bool(repo.db.execute("SELECT 1 FROM followed_stories WHERE user_id=? AND story_id=? AND expires_at>=?", (uid, story_id, iso(utc_now()))).fetchone())


# ------------------------------------------------------------------ worker
class PersonalAlertService:
    def __init__(self, repo):
        self.repo = repo
        self.notifications = NotificationService(repo)
        self._last = None

    def run_once(self, now=None, force=False):
        if not force and self._last is not None and time.monotonic() - self._last < CHECK_SECONDS:
            return {"status": "NOT_DUE"}
        self._last = time.monotonic()
        now = now or utc_now()
        row = self.repo.db.execute("SELECT value FROM content_index_state WHERE key=?", (STATE_KEY,)).fetchone()
        since = parse(row["value"]) if row else now - timedelta(minutes=15)
        since = max(since, now - timedelta(hours=6))   # a long outage does not replay a day of news
        result = {"status": "CHECKED", "keyword_alerts": self.check_keywords(since, now), "story_updates": self.check_stories(now)}
        self.repo.db.execute("INSERT INTO content_index_state(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                             (STATE_KEY, iso(now), iso(now)))
        self.repo.db.commit()
        return result

    def _premium(self, uid):
        from .subscriptions import has_premium_features
        return has_premium_features(self.repo, uid)

    def _new_articles(self, since, now):
        return self.repo.db.execute("""SELECT id,title,description,event_id,source_language,image_url,url,published_at FROM indexed_content
            WHERE COALESCE(first_seen_at,indexed_at)>? AND COALESCE(first_seen_at,indexed_at)<=? AND published_at>=?
            ORDER BY lower(COALESCE(source_language,'')) LIKE 'pt%' DESC,published_at DESC""",
            (iso(since), iso(now), iso(now - timedelta(hours=12)))).fetchall()

    def _enqueue(self, uid, kind, delivery_id, payload, now):
        if not wants(self.notifications.settings(uid), kind):
            return 0
        message = {**payload, "data": {"type": kind, **payload["data"]}}
        created = 0
        for device in self.repo.db.execute("SELECT id FROM push_devices WHERE user_id=? AND enabled=1 AND invalidated_at IS NULL", (uid,)).fetchall():
            created += self.repo.db.execute(
                """INSERT INTO notification_jobs(id,user_id,delivery_id,device_id,notification_type,scheduled_for,status,attempt_count,
                   max_attempts,next_attempt_at,provider_message_id,last_error,created_at,updated_at,payload_json)
                   VALUES(?,?,?,?,?,?,'PENDING',0,3,NULL,NULL,NULL,?,?,?) ON CONFLICT DO NOTHING""",
                ("notification_" + uuid.uuid4().hex, uid, delivery_id, device["id"], kind, iso(now), iso(now), iso(now),
                 json.dumps(message, ensure_ascii=False))).rowcount
        self.repo.db.commit()
        return created

    def _sent_today(self, uid, kind, now, like=None):
        sql = "SELECT COUNT(DISTINCT delivery_id) FROM notification_jobs WHERE user_id=? AND notification_type=? AND created_at>=? AND status<>'CANCELLED'"
        params = [uid, kind, iso(now - timedelta(hours=24))]
        if like:
            sql += " AND delivery_id LIKE ?"; params.append(like)
        return self.repo.db.execute(sql, params).fetchone()[0]

    def check_keywords(self, since, now):
        from .breaking import BreakingNewsService, already_told, story_summary
        from .content import readable
        keywords = {}
        for row in self.repo.db.execute("""SELECT k.* FROM keyword_alerts k JOIN users u ON u.id=k.user_id WHERE u.status='ACTIVE'"""):
            keywords.setdefault(row["user_id"], []).append(row)
        if not keywords:
            return 0
        articles = self._new_articles(since, now)
        if not articles:
            return 0
        quiet = BreakingNewsService(self.repo); sent = 0
        for uid, rows in keywords.items():
            if not self._premium(uid):
                continue
            prefs = self.repo.get_preferences(uid) or {}
            if not quiet._awake(prefs, now):
                continue
            stories = set()
            for keyword in rows:
                pattern = keyword_pattern(keyword["keyword"])
                for article in articles:
                    story = article["event_id"] or article["id"]
                    if story in stories or not pattern.search(fold(article["title"])):
                        continue
                    if not readable(article["source_language"], prefs.get("language") or "pt-BR"):
                        continue
                    if (self._sent_today(uid, "KEYWORD_ALERT", now) >= KEYWORD_ALERTS_PER_DAY
                            or self._sent_today(uid, "KEYWORD_ALERT", now, f"keyword:{keyword['id']}:%") >= KEYWORD_ALERTS_PER_KEYWORD):
                        break
                    members = {article["id"]} | ({row[0] for row in self.repo.db.execute("SELECT id FROM indexed_content WHERE event_id=?", (article["event_id"],))}
                                                 if article["event_id"] else set())
                    if already_told(self.repo, uid, members, article["title"], now):
                        stories.add(story); continue
                    stories.add(story)
                    payload = {"title": article["title"], "body": f"“{keyword['keyword']}” · " + (story_summary(article["title"], [article["description"]]) or "Toque para ler a matéria."),
                               "data": {"story_id": article["id"], "keyword": keyword["keyword"]}}
                    if article["image_url"] and str(article["image_url"]).startswith("https://"):
                        payload["data"]["image"] = article["image_url"]
                    sent += self._enqueue(uid, "KEYWORD_ALERT", f"keyword:{keyword['id']}:story:{story}", payload, now)
        return sent

    def check_stories(self, now):
        from .breaking import story_summary
        from .content import readable
        sent = 0
        self.repo.db.execute("DELETE FROM followed_stories WHERE expires_at<?", (iso(now),))
        self.repo.db.commit()
        for follow in self.repo.db.execute("""SELECT f.* FROM followed_stories f JOIN users u ON u.id=f.user_id WHERE u.status='ACTIVE'""").fetchall():
            if follow["last_notified_at"] and parse(follow["last_notified_at"]) > now - STORY_UPDATE_GAP:
                continue
            event_id = follow["event_id"] or (self.repo.db.execute("SELECT event_id FROM indexed_content WHERE id=?", (follow["story_id"],)).fetchone() or {"event_id": None})["event_id"]
            if not event_id:
                continue
            if not follow["event_id"]:
                self.repo.db.execute("UPDATE followed_stories SET event_id=? WHERE user_id=? AND story_id=?", (event_id, follow["user_id"], follow["story_id"]))
            prefs = self.repo.get_preferences(follow["user_id"]) or {}
            update = next((row for row in self.repo.db.execute(
                """SELECT id,title,description,source_name,source_language,image_url FROM indexed_content
                   WHERE event_id=? AND id<>? AND published_at>? AND COALESCE(first_seen_at,indexed_at)>?
                   ORDER BY lower(COALESCE(source_language,'')) LIKE 'pt%' DESC,published_at DESC""",
                (event_id, follow["story_id"], follow["last_update_at"], follow["last_update_at"])).fetchall()
                if readable(row["source_language"], prefs.get("language") or "pt-BR")), None)
            if not update or not self._premium(follow["user_id"]):
                continue
            payload = {"title": f"Novidade: {follow['headline']}"[:120], "body": update["title"] if not update["description"] else
                       (story_summary(update["title"], [update["description"]]) or update["title"]),
                       "data": {"story_id": update["id"], "followed_story_id": follow["story_id"]}}
            sent += self._enqueue(follow["user_id"], "STORY_UPDATE", f"story_update:{follow['story_id']}:{update['id']}", payload, now)
            self.repo.db.execute("UPDATE followed_stories SET last_update_at=?,last_notified_at=? WHERE user_id=? AND story_id=?",
                                 (iso(now), iso(now), follow["user_id"], follow["story_id"]))
            self.repo.db.commit()
        return sent
