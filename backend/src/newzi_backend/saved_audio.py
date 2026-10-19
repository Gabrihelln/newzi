"""Saved stories as audio (Premium): "Ouvir as matérias salvas", the last item of the app's listening queue.

The person's most recent saved stories still unread (up to SAVED_AUDIO_STORIES) become an edition of their own,
narrated by the regular audio pipeline (worker ``audio`` role) with the person's voice. The edition is keyed by
the stories it holds, so it is narrated again only when the list changes.
"""
import hashlib
import json
import os
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from .timeutil import now_iso

SAVED_AUDIO_STORIES = int(os.getenv("SAVED_AUDIO_STORIES", "12"))


def _stories(repo, uid):
    rows = repo.db.execute("""SELECT s.story_id,s.story_json FROM saved_stories s LEFT JOIN saved_story_progress p
        ON p.user_id=s.user_id AND p.story_id=s.story_id WHERE s.user_id=? AND COALESCE(p.progress,0)<100
        ORDER BY s.saved_at DESC LIMIT ?""", (uid, SAVED_AUDIO_STORIES)).fetchall()
    return [json.loads(row["story_json"]) for row in rows]


def _edition(repo, uid, prefs, stories):
    language = prefs.get("language") or "pt-BR"
    digest = hashlib.sha256(json.dumps([language, [story["id"] for story in stories]]).encode()).hexdigest()[:16]
    profile_key = f"saved_{uid}_{digest}"
    found = repo.db.execute("SELECT id FROM briefing_editions WHERE profile_key=?", (profile_key,)).fetchone()
    if found:
        return found["id"]
    edition_id = "edition_" + uuid.uuid4().hex; now = now_iso()
    local_date = datetime.now(ZoneInfo(prefs.get("timezone") or "UTC")).date().isoformat()
    repo.db.execute("""INSERT INTO briefing_editions(id,profile_key,edition_date,language,status,generated_at,item_count,engine_version,created_at,user_id,narration)
        VALUES(?,?,?,?,'READY',?,?,'saved_audio',?,?,'saved')""", (edition_id, profile_key, local_date, language, now, len(stories), now, uid))
    for position, story in enumerate(stories, 1):
        repo.db.execute("""INSERT INTO briefing_edition_items(id,edition_id,position,event_id,headline,summary,why_it_matters,key_points_json,
            warnings_json,sources_json,created_at,primary_taxonomy_id,primary_taxonomy_label) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("edition_item_" + uuid.uuid4().hex, edition_id, position, story["id"], story.get("headline"), story.get("summary") or story.get("headline"),
             story.get("why_it_matters"), json.dumps(story.get("key_points") or [], ensure_ascii=False), "[]",
             json.dumps(story.get("sources") or [], ensure_ascii=False), now, story.get("primary_taxonomy_id"), story.get("primary_taxonomy_label")))
    repo.db.commit()
    return edition_id


def saved_audio(repo, audio, uid, create=False):
    """The saved stories' audio: status, story count and, when READY, its URL. ``create`` queues it when missing."""
    from .subscriptions import require
    require(repo, uid, "audio_queue")
    prefs = repo.get_preferences(uid) or {}
    stories = _stories(repo, uid)
    if not stories:
        return {"status": "EMPTY", "story_count": 0}
    language = prefs.get("language") or "pt-BR"
    edition_id = _edition(repo, uid, prefs, stories)
    voice = audio.effective_voice(prefs.get("audio_voice_id"), language)
    result = audio.request(edition_id, language, voice) if create else audio.audio_for_edition(edition_id, language, voice)
    out = {"status": result.get("status") or "NOT_AVAILABLE", "story_count": len(stories), "edition_id": edition_id,
           "duration_ms": result.get("duration_ms"), "stories": [{"id": story["id"], "headline": story.get("headline")} for story in stories]}
    if out["status"] == "READY":
        out["audio_url"] = f"/api/v1/me/saved/audio/file?edition={edition_id}&v={result.get('asset_version') or ''}"
    return out


def saved_audio_file(repo, audio, uid, edition_id):
    from .product_backend import not_found
    from .subscriptions import require
    require(repo, uid, "audio_queue")
    row = repo.db.execute("SELECT language FROM briefing_editions WHERE id=? AND user_id=? AND narration='saved'", (edition_id, uid)).fetchone()
    if not row:
        raise not_found("audio not available")
    voice = audio.effective_voice((repo.get_preferences(uid) or {}).get("audio_voice_id"), row["language"])
    metadata = audio.audio_for_edition(edition_id, row["language"], voice)
    path = audio.artifact_path(edition_id, row["language"], voice) if metadata.get("status") == "READY" else None
    if not path:
        raise not_found("audio not ready")
    return path, metadata.get("mime_type") or "audio/mpeg"
