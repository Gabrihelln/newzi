"""Shared test infrastructure: isolated environment, fake TTS, seed data and normalization.

Importing this module configures the process environment, so it must run before any
``newzi_backend`` import (conftest.py imports it first).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
for entry in (PROJECT_ROOT / "engine" / "src", PROJECT_ROOT / "backend" / "src", PROJECT_ROOT / "backend"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

SESSION_DIR = Path(tempfile.mkdtemp(prefix="newzi-tests-"))
BASE_ENV = {
    "APP_ENV": "development",
    "ENABLE_DEV_ENDPOINTS": "true",
    "FIREBASE_AUTH_ENABLED": "false",
    "BRIEFING_GENERATOR": "fixture",
    "AUDIO_ENABLED": "true",
    "TTS_PROVIDER": "edge-tts",
    "TTS_VOICE": "newzi_lucas",
    "NOTIFICATIONS_ENABLED": "true",
    "PUSH_PROVIDER": "development",
    "DEFAULT_TIMEZONE": "America/Sao_Paulo",
    "DEFAULT_LANGUAGE": "pt-BR",
    # No installed models: narration stays in the source language, deterministically.
    "TRANSLATION_MODELS_DIR": str(SESSION_DIR / "no-translation-models"),
    "NEWS_ENGINE_DATA_DIR": str(SESSION_DIR / "engine"),
}
os.environ.update(BASE_ENV)
# The product API loads the repository .env with setdefault; keep developer values out of tests.
os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)


def fresh_environment(database_url=None):
    """Point the backend at a brand-new database and audio storage; returns the run directory."""
    run_dir = SESSION_DIR / ("run_" + uuid.uuid4().hex[:8])
    (run_dir / "audio" / "tmp").mkdir(parents=True)
    os.environ.update(BASE_ENV)
    os.environ["AUDIO_STORAGE_ROOT"] = str(run_dir / "audio")
    os.environ["NEWS_AUDIO_TMP"] = str(run_dir / "audio" / "tmp")
    os.environ["DATABASE_URL"] = database_url or ("sqlite:///" + (run_dir / "product.sqlite3").as_posix())
    return run_dir


# ---------------------------------------------------------------- fake TTS
def _silent_mp3(path, seconds):
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                    "-t", str(seconds), "-c:a", "libmp3lame", "-b:a", "32k", "-map_metadata", "-1",
                    "-fflags", "+bitexact", "-flags:a", "+bitexact", "-y", str(path)], check=True, capture_output=True)


def install_fake_tts():
    """Replace the online Edge voices with deterministic local silence (ffmpeg)."""
    from newzi_backend import audio

    def list_voices(self):
        return [entry["provider_voice"] for entry in audio.VOICE_CATALOG[self.name]]

    def synthesize(self, text, voice, language, options=None):
        out = Path(os.environ["NEWS_AUDIO_TMP"]) / ("tts_" + uuid.uuid4().hex + ".mp3")
        _silent_mp3(out, 1)
        return {"path": str(out), "mime_type": "audio/mpeg", "duration_ms": 1000,
                "size_bytes": out.stat().st_size, "resolved_voice": voice}

    def synthesize_segments(self, segments, voice, language, options=None):
        out = Path(os.environ["NEWS_AUDIO_TMP"]) / ("tts_briefing_" + uuid.uuid4().hex + ".mp3")
        _silent_mp3(out, len(segments))
        timings = [(segment["id"], index * 1000, (index + 1) * 1000) for index, segment in enumerate(segments)]
        return {"path": str(out), "mime_type": "audio/mpeg", "duration_ms": len(segments) * 1000,
                "size_bytes": out.stat().st_size, "segment_timings": timings, "resolved_voice": voice}

    audio.EdgeTTSProvider.list_voices = list_voices
    audio.EdgeTTSProvider.health_check = lambda self: True
    audio.EdgeTTSProvider.synthesize = synthesize
    audio.EdgeTTSProvider.synthesize_segments = synthesize_segments


# ---------------------------------------------------------------- seed data
SEED_TOPICS = ("TECHNOLOGY", "ECONOMY")


def seed_content(repo, topics=SEED_TOPICS):
    """Index a small deterministic article pool (no network, no classifier)."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows = []
    for index in range(8):
        topic = topics[index % len(topics)]
        published = (now - timedelta(hours=index + 1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        rows.append({
            "id": f"article_{index:02d}", "content_hash": f"hash_{index:02d}",
            "title": f"Manchete {index} sobre {topic}", "description": f"Resumo da notícia {index} sobre {topic}.",
            "url": f"https://news.example/{index}", # article_01 has no picture: it stays out of the news lists and keeps the image endpoint's 404 offline.
            "image_url": None if index == 1 else f"https://news.example/images/{index}.jpg", "source_name": f"Fonte {index % 3}", "source_id": f"source_{index % 3}",
            "source_country": "BR" if index % 2 else "US", "source_language": "pt-BR" if index % 2 else "en",
            "published_at": published, "indexed_at": published, "enrichment_mode": "test",
            "quality_score": 5.0 + index, "event_id": f"event_{index:02d}", "topic": topic,
        })
    for row in rows:
        topic = row.pop("topic")
        columns = ",".join(row)
        repo.db.execute(f"INSERT INTO indexed_content({columns}) VALUES({','.join('?' for _ in row)})", tuple(row.values()))
        repo.db.execute("INSERT INTO content_taxonomy(content_id,taxonomy_id,score) VALUES(?,?,?)", (row["id"], topic, 8.0))
    repo.db.commit()
    return rows


# ---------------------------------------------------------------- normalization
_ID = re.compile(r"\b([a-z]+(?:_[a-z]+)*_[0-9a-f]{12,})\b")
_TS = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?")
_HEX = re.compile(r"\b[0-9a-f]{32,}\b")
_DURATION_KEYS = re.compile(r"_(ms|minutes)(_|$)")
_KEEP_MS = {"duration_ms", "audio_duration_ms", "segment_start_ms", "segment_end_ms", "estimated_duration_ms"}


class Normalizer:
    """Replace volatile values (ids, timestamps, hashes, timings) with stable placeholders."""
    def __init__(self):
        self.ids = {}

    def _id(self, match):
        value = match.group(1); prefix = value.rsplit("_", 1)[0]
        if value not in self.ids:
            self.ids[value] = f"<{prefix}#{sum(1 for v in self.ids if v.rsplit('_', 1)[0] == prefix) + 1}>"
        return self.ids[value]

    def text(self, value):
        # Temporary paths differ per run and per OS (Windows profiles may contain spaces and use backslashes).
        value = re.sub(r"[^\"']*newzi-tests-\w+[\\/]run_[0-9a-f]{8}", "<run>", value)
        if value.startswith("<run>"): value = value.replace("\\", "/")
        value = _ID.sub(self._id, value)
        value = _TS.sub("<ts>", value)
        value = _HEX.sub("<hex>", value)
        today = datetime.now(timezone.utc).date()
        for offset in (-1, 0, 1):  # the user's local date may differ from UTC
            value = value.replace((today + timedelta(days=offset)).isoformat(), "<date>")
        return value

    def _field(self, key, value, timings=False):
        if timings and key == "duration_ms":
            return "<number>"
        if key == "token" and isinstance(value, str):
            return "<token>"
        if key == "request_id" and isinstance(value, str):
            return "<request_id>"
        if key == "next_briefing" and isinstance(value, dict):
            # Today or tomorrow depends on the hour the suite runs.
            return {**self(value), "day": "<day>"}
        if _DURATION_KEYS.search(key) and key not in _KEEP_MS:
            # Timings vary run to run; keep only the shape.
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return "<number>"
            if isinstance(value, dict):
                return {k: "<number>" if isinstance(v, (int, float)) and not isinstance(v, bool) else self(v) for k, v in value.items()}
        return self(value, key)

    def __call__(self, value, key=None):
        if isinstance(value, dict):
            # Rows under a "*phases" key are measured timings, not stored media durations.
            timings = bool(key) and key.endswith("phases")
            return {k: self._field(k, v, timings) for k, v in value.items()}
        if isinstance(value, list):
            return [self(v, key) for v in value]
        if isinstance(value, str):
            return self.text(value)
        return value


def load_golden(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def reset_postgres(database_url):
    """Give a PostgreSQL test database an empty public schema."""
    import psycopg
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS public CASCADE")
        connection.execute("CREATE SCHEMA public")


def cleanup():
    shutil.rmtree(SESSION_DIR, ignore_errors=True)
