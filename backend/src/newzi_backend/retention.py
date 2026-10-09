"""Bounded data retention for the product database, audio storage and the engine cache.

What is removed is never user-visible history: briefings, deliveries and saved items keep
their own snapshots. Audio variants are removed only when no delivery uses them.

    RETENTION_AUDIO_VARIANT_DAYS  unused audio variants (default 7)
    RETENTION_TELEMETRY_DAYS      events, phases, finished jobs and runs (default 30)
    RETENTION_CONTENT_DAYS        indexed and collected articles (default 90)

Run once by hand with:  python -m newzi_backend.retention
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)
STATE_KEY = "retention_last_run"


def _days(name, default):
    return max(1, int(os.getenv(name, str(default))))


def _iso(moment):
    return moment.isoformat()


def _stale_audio_variants(repo, storage, cutoff):
    """Delete audio artifacts no delivery points to (replaced voices, regenerations)."""
    rows = repo.db.execute("""SELECT a.id,a.storage_path,a.voice,a.language,s.edition_id,s.script_version
        FROM audio_artifacts a JOIN audio_scripts s ON s.id=a.audio_script_id
        WHERE a.created_at<?
        AND NOT EXISTS (SELECT 1 FROM user_briefing_deliveries d WHERE d.audio_artifact_id=a.id)
        AND NOT EXISTS (SELECT 1 FROM manual_refresh_requests m WHERE m.audio_variant_id=a.id AND m.status IN ('PENDING','GENERATING'))""",
        (_iso(cutoff),)).fetchall()
    removed = freed = 0
    for row in rows:
        path = storage.resolve(row["storage_path"]) if row["storage_path"] else None
        size = path.stat().st_size if path else 0
        repo.db.execute("DELETE FROM audio_artifact_segments WHERE artifact_id=?", (row["id"],))
        repo.db.execute("DELETE FROM audio_artifacts WHERE id=?", (row["id"],))
        # Without the artifact, a READY job would report audio that no longer exists.
        repo.db.execute("DELETE FROM audio_generation_jobs WHERE edition_id=? AND language=? AND voice=? AND status='READY'",
                        (row["edition_id"], row["language"], row["voice"]))
        repo.db.commit()
        # Identical audio is stored once by checksum; keep the file while another artifact uses it.
        if path and not repo.db.execute("SELECT 1 FROM audio_artifacts WHERE storage_path=?", (row["storage_path"],)).fetchone():
            path.unlink(missing_ok=True); freed += size
        removed += 1
    return {"audio_variants_removed": removed, "audio_bytes_freed": freed}


def _orphan_audio_files(repo, storage, older_than):
    """Remove files in the audio root that no artifact references (failed moves, TTS leftovers)."""
    referenced = {Path(row[0]).name for row in repo.db.execute("SELECT storage_path FROM audio_artifacts WHERE storage_path IS NOT NULL")}
    removed = freed = 0
    for candidate in storage.root.iterdir():
        if not candidate.is_file() or candidate.name in referenced:
            continue
        if candidate.suffix.lower() not in {".mp3", ".wav", ".m4a", ".aac", ".tmp", ".txt"} and not candidate.name.endswith(".tmp"):
            continue
        if datetime.fromtimestamp(candidate.stat().st_mtime, timezone.utc) >= older_than:
            continue  # may belong to a synthesis in progress
        freed += candidate.stat().st_size; candidate.unlink(missing_ok=True); removed += 1
    return {"orphan_audio_files_removed": removed, "orphan_audio_bytes_freed": freed}


def _telemetry(repo, cutoff):
    stamp = _iso(cutoff); date = cutoff.date().isoformat(); counts = {}
    statements = {
        "audio_events": ("DELETE FROM audio_events WHERE created_at<?", stamp),
        "notification_events": ("DELETE FROM notification_events WHERE created_at<?", stamp),
        "notification_jobs": ("DELETE FROM notification_jobs WHERE status IN ('SENT','FAILED','CANCELLED') AND updated_at<?", stamp),
        "generation_job_phases": ("DELETE FROM generation_job_phases WHERE job_id IN (SELECT id FROM generation_jobs WHERE briefing_date<? AND status IN ('COMPLETED','FAILED'))", date),
        "generation_jobs": ("DELETE FROM generation_jobs WHERE briefing_date<? AND status IN ('COMPLETED','FAILED')", date),
        "audio_job_phases": ("DELETE FROM audio_job_phases WHERE finished_at<?", stamp),
        "manual_refresh_requests": ("DELETE FROM manual_refresh_requests WHERE status IN ('READY','FAILED') AND updated_at<?", stamp),
        "content_ingestion_runs": ("DELETE FROM content_ingestion_runs WHERE status<>'RUNNING' AND started_at<?", stamp),
        "auth_sessions": ("DELETE FROM auth_sessions WHERE expires_at<? OR revoked_at<?", None),
    }
    for name, (sql, value) in statements.items():
        params = (stamp, stamp) if value is None else (value,)
        counts[name] = repo.db.execute(sql, params).rowcount
    repo.db.commit()
    return {"telemetry_rows_removed": counts}


def _old_content(repo, cutoff):
    stamp = _iso(cutoff)
    old = "SELECT id FROM indexed_content WHERE COALESCE(published_at,indexed_at)<?"
    repo.db.execute(f"DELETE FROM content_enrichment WHERE content_id IN ({old})", (stamp,))
    repo.db.execute(f"DELETE FROM content_taxonomy WHERE content_id IN ({old})", (stamp,))
    removed = repo.db.execute("DELETE FROM indexed_content WHERE COALESCE(published_at,indexed_at)<?", (stamp,)).rowcount
    repo.db.commit()
    engine_removed = 0
    try:
        from newzi_engine.storage import Store
        engine_removed = Store().purge_older_than(cutoff)
    except Exception:
        log.exception("engine article retention failed")
    return {"indexed_content_removed": removed, "engine_articles_removed": engine_removed}


def run_retention(repo, storage=None, now=None):
    if storage is None:
        from .audio import AudioStorage
        storage = AudioStorage()
    now = now or datetime.now(timezone.utc)
    result = {}
    result.update(_stale_audio_variants(repo, storage, now - timedelta(days=_days("RETENTION_AUDIO_VARIANT_DAYS", 7))))
    result.update(_orphan_audio_files(repo, storage, now - timedelta(days=1)))
    result.update(_telemetry(repo, now - timedelta(days=_days("RETENTION_TELEMETRY_DAYS", 30))))
    result.update(_old_content(repo, now - timedelta(days=_days("RETENTION_CONTENT_DAYS", 90))))
    repo.db.execute("INSERT INTO content_index_state(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                    (STATE_KEY, _iso(now), _iso(now)))
    repo.db.commit()
    log.info("data retention completed %s", result)
    return result


def run_retention_if_due(repo, interval_seconds=86400, storage=None, now=None):
    now = now or datetime.now(timezone.utc)
    row = repo.db.execute("SELECT value FROM content_index_state WHERE key=?", (STATE_KEY,)).fetchone()
    if row:
        last = datetime.fromisoformat(row["value"])
        if (now - last).total_seconds() < interval_seconds:
            return {"status": "NOT_DUE"}
    return {"status": "COMPLETED", **run_retention(repo, storage, now)}


if __name__ == "__main__":
    import json
    from .env import load_local_environment
    load_local_environment()
    from .product_backend import ProductRepository
    print(json.dumps(run_retention(ProductRepository()), indent=2))
