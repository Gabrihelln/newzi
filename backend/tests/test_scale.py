"""Scheduler, worker batching, retention, search, migrations and auth caching."""
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

import support
from conftest import add_user

POSTGRES = bool(os.getenv("TEST_DATABASE_URL"))


# ---------------------------------------------------------------- scheduler
def test_scheduler_schedules_each_due_user_once(repo):
    from newzi_backend.scheduling import BriefingScheduler, FixedClock
    add_user(repo, "due", "UTC", "06:00")
    add_user(repo, "sao_paulo", "America/Sao_Paulo", "09:00")   # 09:00 local == 12:00 UTC
    add_user(repo, "later", "UTC", "23:00")
    add_user(repo, "inactive", "UTC", "06:00")
    repo.db.execute("UPDATE users SET status='DISABLED' WHERE id='inactive'")
    repo.db.execute("INSERT INTO users(id,email,display_name,language,timezone,created_at,updated_at,status) VALUES('no_prefs','n@x','n','pt-BR','UTC','t','t','ACTIVE')")
    repo.db.commit()
    scheduler = BriefingScheduler(repo, clock=FixedClock(datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)), lead_minutes=10)

    first = scheduler.run_once()
    assert (first["jobs_discovered"], first["jobs_created"], first["jobs_skipped_existing"]) == (2, 2, 0)
    jobs = {row["user_id"]: row["briefing_date"] for row in repo.db.execute("SELECT user_id,briefing_date FROM generation_jobs")}
    assert jobs == {"due": "2026-10-10", "sao_paulo": "2026-10-10"}

    second = scheduler.run_once()
    assert (second["jobs_created"], second["jobs_skipped_existing"]) == (0, 2)

    repo.save_preferences("due", {"topics": ["ECONOMY"]})
    third = scheduler.run_once()
    assert third["jobs_created"] == 1
    assert repo.db.execute("SELECT status FROM generation_jobs WHERE user_id='due'").fetchone()[0] == "PENDING"


# ---------------------------------------------------------------- delivery worker
def test_delivery_worker_batches_audio_and_push_without_waiting_for_refresh(repo, monkeypatch):
    from newzi_backend import scheduling
    from newzi_backend.notifications import NotificationService, PushResult
    support.install_fake_tts()
    refresh_started = threading.Event(); release_refresh = threading.Event()

    def slow_refresh(self, force=False):
        refresh_started.set(); release_refresh.wait(10); return {"status": "READY"}
    monkeypatch.setattr(scheduling.NewsRefreshWorker, "refresh_if_due", slow_refresh)

    delivery_time = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%H:%M")
    worker = scheduling.BriefingDeliveryWorker(repo, generator=scheduling.FixtureBriefingGenerator())
    sent = []

    class Recording:
        name = "recording"
        def send(self, token, title, body, data): sent.append(token); return PushResult(True, "m")
    worker.notifications = NotificationService(repo, provider=Recording())
    for index in range(3):
        uid = f"user{index}"
        add_user(repo, uid, "UTC", delivery_time)
        repo.save_preferences(uid, {"audio_voice_id": "newzi_lucas"})
        worker.scheduler.schedule_user_now(uid)
        worker.notifications.register_device(uid, {"platform": "ANDROID", "push_token": f"push-token-{index:04d}"})

    started = time.monotonic()
    result = worker.run_once()
    assert refresh_started.is_set() and time.monotonic() - started < 60, "the cycle must not wait for news collection"
    assert result["news_refresh"]["status"] == "STARTED"
    assert result["generation"]["jobs_completed"] == 3
    assert result["generation"]["edition_generation_count"] == 3, "every user gets an edition composed at their own time"
    owners = [row[0] for row in repo.db.execute("SELECT user_id FROM briefing_editions ORDER BY user_id")]
    assert owners == ["user0", "user1", "user2"]
    assert result["audio"]["jobs_completed"] >= 1
    statuses = {row[0] for row in repo.db.execute("SELECT audio_status FROM user_briefing_deliveries")}
    assert statuses == {"READY"}
    assert worker.run_once()["news_refresh"]["status"] == "RUNNING_IN_BACKGROUND"
    release_refresh.set(); worker._refresh_thread.join(10)

    # All due pushes go out in one batch (one per worker cycle before).
    delivered = worker.notifications.run_batch(limit=50, now=datetime.now(timezone.utc) + timedelta(hours=1, minutes=1))
    assert delivered["notifications_sent"] == 3 and len(sent) == 3


# ---------------------------------------------------------------- retention
def _artifact(repo, artifact_id, edition_id, voice, created, storage_root, checksum):
    path = storage_root / (checksum + ".mp3"); path.write_bytes(b"x" * 256)
    repo.db.execute("INSERT INTO audio_scripts(id,edition_id,language,target_duration_seconds,estimated_duration_seconds,script_version,status,created_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                    ("script_" + edition_id, edition_id, "pt-BR", 300, 60, "v3", "READY", created))
    repo.db.execute("""INSERT INTO audio_artifacts(id,audio_script_id,status,provider,voice,language,mime_type,storage_path,duration_ms,size_bytes,checksum,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (artifact_id, "script_" + edition_id, "READY", "edge-tts", voice, "pt-BR", "audio/mpeg", str(path), 1000, 256, checksum, created))
    repo.db.execute("""INSERT INTO audio_generation_jobs(id,edition_id,language,voice,script_version,status,created_at) VALUES(?,?,?,?,?,?,?)""",
                    ("job_" + artifact_id, edition_id, "pt-BR", voice, "v3:edge-tts:test", "READY", created))
    return path


def test_retention_removes_only_unused_and_expired_data(repo):
    from newzi_backend.audio import AudioStorage
    from newzi_backend.retention import run_retention, run_retention_if_due
    storage = AudioStorage(); now = datetime.now(timezone.utc); old = (now - timedelta(days=10)).isoformat(); recent = now.isoformat()
    add_user(repo, "u1")
    used = _artifact(repo, "artifact_used", "edition_a", "newzi_lucas", old, storage.root, "a" * 64)
    replaced = _artifact(repo, "artifact_replaced", "edition_a", "newzi_clara", old, storage.root, "b" * 64)
    fresh = _artifact(repo, "artifact_fresh", "edition_a", "newzi_sofia", recent, storage.root, "c" * 64)
    repo.db.execute("""INSERT INTO user_briefing_deliveries(id,user_id,edition_id,local_date,delivery_time,timezone,status,created_at,audio_artifact_id)
        VALUES('delivery_1','u1','edition_a','2026-01-01','06:00','UTC','READY',?,'artifact_used')""", (old,))
    orphan_old = storage.root / "tts_leftover.mp3"; orphan_old.write_bytes(b"y" * 10)
    two_days_ago = (now - timedelta(days=2)).timestamp(); os.utime(orphan_old, (two_days_ago, two_days_ago))
    orphan_new = storage.root / "tts_in_progress.mp3"; orphan_new.write_bytes(b"z" * 10)
    support.seed_content(repo)
    repo.db.execute("UPDATE indexed_content SET published_at=? WHERE id='article_00'", ((now - timedelta(days=200)).isoformat(),))
    repo.db.execute("INSERT INTO audio_events(event_type,metadata_json,created_at) VALUES('old','{}',?)", ((now - timedelta(days=60)).isoformat(),))
    repo.db.commit()

    result = run_retention(repo, storage, now)
    remaining = {row[0] for row in repo.db.execute("SELECT id FROM audio_artifacts")}
    assert remaining == {"artifact_used", "artifact_fresh"}
    assert used.exists() and fresh.exists() and not replaced.exists()
    assert not repo.db.execute("SELECT 1 FROM audio_generation_jobs WHERE id='job_artifact_replaced'").fetchone()
    assert not orphan_old.exists() and orphan_new.exists()
    assert result["indexed_content_removed"] == 1
    assert not repo.db.execute("SELECT 1 FROM content_taxonomy WHERE content_id='article_00'").fetchone()
    assert result["telemetry_rows_removed"]["audio_events"] == 1
    assert run_retention_if_due(repo, storage=storage, now=now + timedelta(hours=1)) == {"status": "NOT_DUE"}


# ---------------------------------------------------------------- search
def test_news_search_ignores_accents_and_matches_prefixes(repo):
    add_user(repo, "reader", topics=("ECONOMY",))
    support.seed_content(repo)
    now = datetime.now(timezone.utc).isoformat()
    repo.db.execute("""INSERT INTO indexed_content(id,content_hash,title,description,url,source_name,source_id,source_language,published_at,indexed_at,enrichment_mode,image_url)
        VALUES('article_accent','h','Inflação dispara no Brasil','Preços sobem em São Paulo','https://n.example/a','Fonte','source_9','pt-BR',?,?,'test','https://n.example/a.jpg')""", (now, now))
    repo.db.commit()

    def found(query):
        return {item["id"] for item in repo.latest_news("reader", 30, query=query, discovery=True)}
    assert "article_accent" in found("inflacao")
    assert "article_accent" in found("INFLA brasil")
    assert "article_accent" in found("sao paulo")
    assert "article_accent" not in found("inflacao argentina")
    assert found("!!!") == set()
    repo.db.execute("UPDATE indexed_content SET title='Juros caem' WHERE id='article_accent'"); repo.db.commit()
    assert "article_accent" not in found("inflacao dispara") and "article_accent" in found("juros")


# ---------------------------------------------------------------- migrations
@pytest.mark.skipif(POSTGRES, reason="upgrades a legacy SQLite file")
def test_migrations_upgrade_a_legacy_sqlite_database(tmp_path):
    legacy = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(legacy)
    connection.executescript("""
        CREATE TABLE users(id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, display_name TEXT NOT NULL, language TEXT NOT NULL,
            timezone TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, status TEXT NOT NULL);
        CREATE TABLE user_preferences(user_id TEXT PRIMARY KEY REFERENCES users(id), topics_json TEXT NOT NULL, language TEXT NOT NULL,
            country_scope TEXT NOT NULL, briefing_time TEXT NOT NULL, timezone TEXT NOT NULL, briefing_size INTEGER NOT NULL,
            audio_enabled INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL);
        CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
        INSERT INTO users VALUES('old','old@x','Old','pt-BR','UTC','2026-01-02T03:04:05Z','2026-01-02T03:04:05.250000+00:00','ACTIVE');
        INSERT INTO user_preferences VALUES('old','["TECHNOLOGY"]','pt-BR','BOTH','06:00','UTC',10,0,'t');
    """); connection.close()
    from newzi_backend.product_backend import ProductRepository
    repo = ProductRepository(path=legacy)
    user = repo.get_user("old")
    assert user["onboarding_status"] == "NOT_STARTED" and "firebase_uid" in user
    assert repo.get_preferences("old")["content_scope"] == "selected"
    applied = [row[0] for row in repo.db.execute("SELECT id FROM schema_versions ORDER BY id")]
    from newzi_backend.migrations import MIGRATIONS
    assert applied == [name for name, _ in MIGRATIONS]
    # Mixed legacy timestamp formats are rewritten to the single canonical one.
    assert (user["created_at"], user["updated_at"]) == ("2026-01-02T03:04:05.000Z", "2026-01-02T03:04:05.250Z")
    repo.close_thread_connection()
    again = ProductRepository(path=legacy)
    assert again.db.execute("SELECT COUNT(*) FROM schema_versions").fetchone()[0] == len(MIGRATIONS)
    again.close_thread_connection()


# ---------------------------------------------------------------- Firebase token cache
def test_firebase_verification_is_cached_briefly(repo):
    from newzi_backend.firebase_identity import FirebaseAdminIdentityProvider
    add_user(repo, "firebase-uid")
    calls = []

    class FakeAuth:
        def verify_id_token(self, token, check_revoked, clock_skew_seconds):
            calls.append(token); return {"uid": "firebase-uid", "email": "firebase-uid@x", "exp": time.time() + 3600}
    provider = object.__new__(FirebaseAdminIdentityProvider)
    provider.repo = repo; provider.auth = FakeAuth(); provider._state = threading.local()
    provider._verified = {}; provider._verified_lock = threading.Lock(); provider.cache_seconds = 60
    assert provider.resolve("token-a").user_id == "firebase-uid"
    assert provider.resolve("token-a").user_id == "firebase-uid"
    assert calls == ["token-a"]
    provider.cache_seconds = 0
    provider.resolve("token-b"); provider.resolve("token-b")
    assert calls == ["token-a", "token-b", "token-b"]


# ---------------------------------------------------------------- Firebase user rows
def test_simultaneous_first_requests_share_one_user_row(repo):
    # The app's first screen sends several requests at once; none may fail on the unique UID.
    for round_number in range(5):
        uid = f"new-user-{round_number}"
        barrier, results, errors = threading.Barrier(6), [], []

        def first_request():
            try:
                barrier.wait()
                results.append(repo.ensure_firebase_user(uid, f"{uid}@x", "Nova")["id"])
            except Exception as exc:
                errors.append(exc)
            finally:
                repo.close_thread_connection()
        threads = [threading.Thread(target=first_request) for _ in range(6)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        assert not errors and results == [uid] * 6
        assert repo.db.execute("SELECT COUNT(*) FROM users WHERE firebase_uid=?", (uid,)).fetchone()[0] == 1
        assert repo.get_preferences(uid) is not None


def test_an_account_recreated_with_the_same_email_starts_clean(repo):
    # Deleted in the Firebase console: the old row stays here, and the new UID needs its e-mail.
    repo.ensure_firebase_user("old-uid", "teste@x.com", "Antigo")
    repo.save_preferences("old-uid", {"topics": ["SPORTS"]})
    user = repo.ensure_firebase_user("new-uid", "teste@x.com", "Novo", account_exists=lambda uid: uid != "old-uid")
    assert user["id"] == "new-uid" and repo.get_user("old-uid") is None
    assert repo.get_preferences("new-uid")["topics"] != ["SPORTS"]


def test_a_live_account_never_loses_its_email_to_another(repo):
    repo.ensure_firebase_user("owner", "dono@x.com", "Dono")
    assert repo.ensure_firebase_user("other", "dono@x.com", "Outro", account_exists=lambda uid: True) is None
    assert repo.get_user("owner")["email"] == "dono@x.com" and repo.get_user("other") is None
