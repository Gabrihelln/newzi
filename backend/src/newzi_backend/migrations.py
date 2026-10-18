"""Versioned schema migrations for the product database (SQLite and PostgreSQL).

Each migration runs once, in order, inside a transaction that holds the database write
lock, and is recorded in ``schema_versions``. Add new changes as a new numbered entry in
MIGRATIONS; never edit one that has shipped.

Column declarations use portable types (TEXT, INTEGER, REAL, AUTO for an auto-increment
key); render() maps them to each dialect. The baseline also upgrades databases created by
the earlier ad-hoc ``ensure_*_schema`` functions: missing tables, columns and indexes are
added, existing data is kept.
"""
from datetime import datetime, timedelta, timezone

from .db import POSTGRES, SQLITE
from .timeutil import iso, now_iso

# table -> (columns [(name, declaration)], table constraints)
BASELINE_TABLES = {
    "topics": ([
        ("code", "TEXT PRIMARY KEY"), ("name", "TEXT NOT NULL"), ("active", "INTEGER NOT NULL DEFAULT 1"),
        ("slug", "TEXT"), ("parent_id", "TEXT"), ("type", "TEXT"),
    ], []),
    "taxonomy_aliases": ([("alias", "TEXT PRIMARY KEY"), ("code", "TEXT NOT NULL REFERENCES topics(code)")], []),
    "taxonomy_resolution_metrics": ([("name", "TEXT PRIMARY KEY"), ("count", "INTEGER NOT NULL DEFAULT 0")], []),
    "users": ([
        ("id", "TEXT PRIMARY KEY"), ("email", "TEXT UNIQUE NOT NULL"), ("display_name", "TEXT NOT NULL"),
        ("language", "TEXT NOT NULL"), ("timezone", "TEXT NOT NULL"), ("created_at", "TEXT NOT NULL"),
        ("updated_at", "TEXT NOT NULL"), ("status", "TEXT NOT NULL"), ("firebase_uid", "TEXT"),
        ("password_hash", "TEXT"), ("onboarding_status", "TEXT NOT NULL DEFAULT 'NOT_STARTED'"),
    ], []),
    "user_preferences": ([
        ("user_id", "TEXT PRIMARY KEY REFERENCES users(id)"), ("topics_json", "TEXT NOT NULL"), ("language", "TEXT NOT NULL"),
        ("country_scope", "TEXT NOT NULL"), ("briefing_time", "TEXT NOT NULL"), ("timezone", "TEXT NOT NULL"),
        ("briefing_size", "INTEGER NOT NULL"), ("audio_enabled", "INTEGER NOT NULL DEFAULT 0"), ("updated_at", "TEXT NOT NULL"),
        ("content_scope", "TEXT NOT NULL DEFAULT 'selected'"), ("audio_voice_id", "TEXT"),
    ], []),
    "auth_sessions": ([
        ("token_hash", "TEXT PRIMARY KEY"), ("user_id", "TEXT NOT NULL REFERENCES users(id)"), ("created_at", "TEXT NOT NULL"),
        ("expires_at", "TEXT NOT NULL"), ("revoked_at", "TEXT"),
    ], []),
    "saved_stories": ([
        ("user_id", "TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE"), ("story_id", "TEXT NOT NULL"),
        ("story_json", "TEXT NOT NULL"), ("saved_at", "TEXT NOT NULL"),
    ], ["PRIMARY KEY(user_id,story_id)"]),
    "saved_story_progress": ([
        ("user_id", "TEXT NOT NULL"), ("story_id", "TEXT NOT NULL"), ("progress", "REAL NOT NULL DEFAULT 0"), ("updated_at", "TEXT NOT NULL"),
    ], ["PRIMARY KEY(user_id,story_id)",
        "FOREIGN KEY(user_id,story_id) REFERENCES saved_stories(user_id,story_id) ON DELETE CASCADE"]),
    "article_feedback": ([
        ("user_id", "TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE"), ("story_id", "TEXT NOT NULL"),
        ("rating", "INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5)"), ("updated_at", "TEXT NOT NULL"),
    ], ["PRIMARY KEY(user_id,story_id)"]),
    "saved_briefings": ([
        ("user_id", "TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE"), ("briefing_id", "TEXT NOT NULL"), ("saved_at", "TEXT NOT NULL"),
    ], ["PRIMARY KEY(user_id,briefing_id)"]),
    # Scheduling, editions and deliveries
    "generation_jobs": ([
        ("id", "TEXT PRIMARY KEY"), ("user_id", "TEXT NOT NULL"), ("briefing_date", "TEXT NOT NULL"), ("scheduled_for", "TEXT NOT NULL"),
        ("delivery_time", "TEXT NOT NULL"), ("timezone", "TEXT NOT NULL"), ("status", "TEXT NOT NULL"),
        ("attempt_count", "INTEGER NOT NULL DEFAULT 0"), ("max_attempts", "INTEGER NOT NULL DEFAULT 2"), ("created_at", "TEXT NOT NULL"),
        ("started_at", "TEXT"), ("finished_at", "TEXT"), ("next_retry_at", "TEXT"), ("error_code", "TEXT"), ("error_message", "TEXT"),
        ("profile_key", "TEXT NOT NULL"), ("worker_id", "TEXT"),
    ], ["UNIQUE(user_id,briefing_date)"]),
    "briefing_editions": ([
        ("id", "TEXT PRIMARY KEY"), ("profile_key", "TEXT NOT NULL"), ("edition_date", "TEXT NOT NULL"), ("language", "TEXT NOT NULL"),
        ("status", "TEXT NOT NULL"), ("generated_at", "TEXT"), ("item_count", "INTEGER NOT NULL DEFAULT 0"), ("engine_version", "TEXT"),
        ("created_at", "TEXT NOT NULL"), ("user_id", "TEXT"),
    ], ["UNIQUE(profile_key,edition_date)"]),
    "briefing_edition_items": ([
        ("id", "TEXT PRIMARY KEY"), ("edition_id", "TEXT NOT NULL"), ("position", "INTEGER NOT NULL"), ("event_id", "TEXT"),
        ("headline", "TEXT"), ("summary", "TEXT"), ("why_it_matters", "TEXT"), ("key_points_json", "TEXT"), ("confidence", "REAL"),
        ("evidence_quality", "TEXT"), ("trace_id", "TEXT"), ("warnings_json", "TEXT"), ("sources_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("created_at", "TEXT NOT NULL"), ("primary_taxonomy_id", "TEXT"), ("primary_taxonomy_label", "TEXT"),
        ("primary_taxonomy_reason", "TEXT"), ("matched_taxonomy_ids_json", "TEXT"), ("user_interest_matches_json", "TEXT"),
    ], []),
    "user_briefing_deliveries": ([
        ("id", "TEXT PRIMARY KEY"), ("user_id", "TEXT NOT NULL"), ("edition_id", "TEXT NOT NULL"), ("local_date", "TEXT NOT NULL"),
        ("delivery_time", "TEXT NOT NULL"), ("timezone", "TEXT NOT NULL"), ("status", "TEXT NOT NULL"), ("created_at", "TEXT NOT NULL"),
        ("delivered_at", "TEXT"), ("selected_voice_id", "TEXT"), ("active_voice_id", "TEXT"), ("audio_artifact_id", "TEXT"),
        ("audio_status", "TEXT NOT NULL DEFAULT 'PENDING'"), ("generation_stage", "TEXT"), ("generation_started_at", "TEXT"),
        ("generation_updated_at", "TEXT"), ("generation_error_code", "TEXT"), ("generation_error_message", "TEXT"),
        ("script_id", "TEXT"), ("voice_fallback_reason", "TEXT"),
    ], ["UNIQUE(user_id,local_date)"]),
    "profile_taxonomy": ([("profile_key", "TEXT NOT NULL"), ("taxonomy_id", "TEXT NOT NULL")], ["PRIMARY KEY(profile_key,taxonomy_id)"]),
    "generation_job_phases": ([
        ("id", "AUTO"), ("job_id", "TEXT NOT NULL"), ("phase", "TEXT NOT NULL"), ("duration_ms", "INTEGER NOT NULL"), ("recorded_at", "TEXT NOT NULL"),
    ], ["UNIQUE(job_id,phase)"]),
    "manual_refresh_requests": ([
        ("id", "TEXT PRIMARY KEY"), ("user_id", "TEXT NOT NULL"), ("reason", "TEXT NOT NULL DEFAULT 'MANUAL_REFRESH'"),
        ("status", "TEXT NOT NULL"), ("stage", "TEXT NOT NULL"), ("requested_at", "TEXT NOT NULL"), ("started_at", "TEXT"),
        ("updated_at", "TEXT NOT NULL"), ("finished_at", "TEXT"), ("ingestion_run_id", "TEXT"), ("edition_id", "TEXT"),
        ("audio_job_id", "TEXT"), ("selected_voice_id", "TEXT"), ("audio_variant_id", "TEXT"), ("error_code", "TEXT"), ("error_message", "TEXT"),
    ], []),
    "content_ingestion_runs": ([
        ("id", "TEXT PRIMARY KEY"), ("status", "TEXT NOT NULL"), ("started_at", "TEXT NOT NULL"), ("completed_at", "TEXT"),
        ("sources_attempted", "INTEGER NOT NULL DEFAULT 0"), ("sources_successful", "INTEGER NOT NULL DEFAULT 0"),
        ("articles_seen", "INTEGER NOT NULL DEFAULT 0"), ("articles_new", "INTEGER NOT NULL DEFAULT 0"),
        ("articles_updated", "INTEGER NOT NULL DEFAULT 0"), ("articles_unchanged", "INTEGER NOT NULL DEFAULT 0"),
        ("errors_json", "TEXT NOT NULL DEFAULT '{}'"), ("source_metrics_json", "TEXT NOT NULL DEFAULT '[]'"),
    ], []),
    "briefing_listening_progress": ([
        ("delivery_id", "TEXT NOT NULL"), ("user_id", "TEXT NOT NULL"), ("progress_seconds", "REAL NOT NULL DEFAULT 0"),
        ("duration_seconds", "REAL NOT NULL DEFAULT 0"), ("completed_at", "TEXT"), ("updated_at", "TEXT NOT NULL"),
    ], ["PRIMARY KEY(delivery_id,user_id)"]),
    # Content index
    "indexed_content": ([
        ("id", "TEXT PRIMARY KEY"), ("content_hash", "TEXT NOT NULL"), ("title", "TEXT NOT NULL"), ("description", "TEXT NOT NULL"),
        ("url", "TEXT NOT NULL"), ("source_name", "TEXT NOT NULL"), ("source_id", "TEXT NOT NULL"), ("source_country", "TEXT"),
        ("source_language", "TEXT"), ("published_at", "TEXT"), ("image_url", "TEXT"), ("image_source", "TEXT"),
        ("image_checked_at", "TEXT"), ("indexed_at", "TEXT NOT NULL"), ("enrichment_mode", "TEXT NOT NULL"), ("first_seen_at", "TEXT"),
        ("last_seen_at", "TEXT"), ("ingested_at", "TEXT"), ("ingestion_run_id", "TEXT"), ("event_id", "TEXT"), ("taxonomy_hash", "TEXT"),
        ("quality_score", "REAL NOT NULL DEFAULT 0"), ("classification_confidence", "REAL"), ("classification_reason", "TEXT"),
    ], []),
    "content_taxonomy": ([
        ("content_id", "TEXT NOT NULL REFERENCES indexed_content(id) ON DELETE CASCADE"), ("taxonomy_id", "TEXT NOT NULL"), ("score", "REAL NOT NULL"),
    ], ["PRIMARY KEY(content_id,taxonomy_id)"]),
    "content_enrichment": ([
        ("content_id", "TEXT NOT NULL"), ("content_hash", "TEXT NOT NULL"), ("prompt_version", "TEXT NOT NULL"), ("schema_version", "TEXT NOT NULL"),
        ("generator_version", "TEXT NOT NULL"), ("output_language", "TEXT NOT NULL"), ("event_id", "TEXT NOT NULL"), ("headline", "TEXT NOT NULL"),
        ("summary", "TEXT NOT NULL"), ("key_points_json", "TEXT NOT NULL"), ("why_it_matters", "TEXT"), ("confidence", "REAL"),
    ], ["PRIMARY KEY(content_id,content_hash,prompt_version,schema_version,generator_version,output_language)"]),
    "content_index_state": ([("key", "TEXT PRIMARY KEY"), ("value", "TEXT NOT NULL"), ("updated_at", "TEXT NOT NULL")], []),
    # Audio
    "audio_scripts": ([
        ("id", "TEXT PRIMARY KEY"), ("edition_id", "TEXT NOT NULL"), ("language", "TEXT NOT NULL"), ("target_duration_seconds", "INTEGER NOT NULL"),
        ("estimated_duration_seconds", "INTEGER NOT NULL"), ("script_version", "TEXT NOT NULL"), ("status", "TEXT NOT NULL"),
        ("created_at", "TEXT NOT NULL"), ("script_hash", "TEXT"),
    ], ["UNIQUE(edition_id,language,script_version)"]),
    "audio_script_segments": ([
        ("id", "TEXT PRIMARY KEY"), ("audio_script_id", "TEXT NOT NULL"), ("position", "INTEGER NOT NULL"), ("type", "TEXT NOT NULL"),
        ("briefing_item_id", "TEXT"), ("text", "TEXT NOT NULL"), ("estimated_duration_ms", "INTEGER NOT NULL"),
        ("segment_start_ms", "INTEGER"), ("segment_end_ms", "INTEGER"), ("created_at", "TEXT NOT NULL"),
    ], []),
    "audio_artifacts": ([
        ("id", "TEXT PRIMARY KEY"), ("audio_script_id", "TEXT NOT NULL"), ("status", "TEXT NOT NULL"), ("provider", "TEXT NOT NULL"),
        ("voice", "TEXT NOT NULL"), ("language", "TEXT NOT NULL"), ("mime_type", "TEXT"), ("storage_path", "TEXT"), ("duration_ms", "INTEGER"),
        ("size_bytes", "INTEGER"), ("checksum", "TEXT"), ("created_at", "TEXT NOT NULL"), ("error_message", "TEXT"), ("resolved_voice", "TEXT"),
    ], ["UNIQUE(audio_script_id,provider,voice,language)"]),
    "audio_generation_jobs": ([
        ("id", "TEXT PRIMARY KEY"), ("edition_id", "TEXT NOT NULL"), ("language", "TEXT NOT NULL"), ("voice", "TEXT NOT NULL"),
        ("script_version", "TEXT NOT NULL"), ("status", "TEXT NOT NULL"), ("attempt_count", "INTEGER NOT NULL DEFAULT 0"),
        ("max_attempts", "INTEGER NOT NULL DEFAULT 3"), ("created_at", "TEXT NOT NULL"), ("started_at", "TEXT"), ("finished_at", "TEXT"),
        ("error_message", "TEXT"), ("next_retry_at", "TEXT"), ("error_code", "TEXT"), ("stage", "TEXT"), ("updated_at", "TEXT"),
    ], ["UNIQUE(edition_id,language,voice,script_version)"]),
    "audio_events": ([
        ("id", "AUTO"), ("event_type", "TEXT NOT NULL"), ("edition_id", "TEXT"), ("artifact_id", "TEXT"),
        ("metadata_json", "TEXT NOT NULL"), ("created_at", "TEXT NOT NULL"),
    ], []),
    "audio_artifact_segments": ([
        ("artifact_id", "TEXT NOT NULL"), ("segment_id", "TEXT NOT NULL"), ("segment_start_ms", "INTEGER NOT NULL"), ("segment_end_ms", "INTEGER NOT NULL"),
    ], ["PRIMARY KEY(artifact_id,segment_id)"]),
    "audio_job_phases": ([
        ("id", "AUTO"), ("audio_job_id", "TEXT NOT NULL"), ("phase", "TEXT NOT NULL"), ("duration_ms", "INTEGER NOT NULL"),
        ("started_at", "TEXT NOT NULL"), ("finished_at", "TEXT NOT NULL"), ("status", "TEXT NOT NULL"), ("error_code", "TEXT"),
    ], ["UNIQUE(audio_job_id,phase)"]),
    # Push notifications
    "push_devices": ([
        ("id", "TEXT PRIMARY KEY"), ("user_id", "TEXT NOT NULL"), ("platform", "TEXT NOT NULL"), ("push_token", "TEXT NOT NULL"),
        ("device_identifier", "TEXT"), ("app_version", "TEXT"), ("locale", "TEXT"), ("timezone", "TEXT NOT NULL"),
        ("enabled", "INTEGER NOT NULL DEFAULT 1"), ("created_at", "TEXT NOT NULL"), ("updated_at", "TEXT NOT NULL"),
        ("last_seen_at", "TEXT NOT NULL"), ("invalidated_at", "TEXT"),
    ], ["UNIQUE(push_token)"]),
    "notification_settings": ([
        ("user_id", "TEXT PRIMARY KEY"), ("notifications_enabled", "INTEGER NOT NULL DEFAULT 1"),
        ("daily_briefing_enabled", "INTEGER NOT NULL DEFAULT 1"), ("breaking_news_enabled", "INTEGER NOT NULL DEFAULT 0"), ("updated_at", "TEXT NOT NULL"),
    ], []),
    "notification_jobs": ([
        ("id", "TEXT PRIMARY KEY"), ("user_id", "TEXT NOT NULL"), ("delivery_id", "TEXT NOT NULL"), ("device_id", "TEXT NOT NULL"),
        ("notification_type", "TEXT NOT NULL"), ("scheduled_for", "TEXT NOT NULL"), ("status", "TEXT NOT NULL"),
        ("attempt_count", "INTEGER NOT NULL DEFAULT 0"), ("max_attempts", "INTEGER NOT NULL DEFAULT 3"), ("next_attempt_at", "TEXT"),
        ("provider_message_id", "TEXT"), ("last_error", "TEXT"), ("created_at", "TEXT NOT NULL"), ("updated_at", "TEXT NOT NULL"),
    ], ["UNIQUE(delivery_id,device_id,notification_type)"]),
    "notification_events": ([
        ("id", "AUTO"), ("event_type", "TEXT NOT NULL"), ("job_id", "TEXT"), ("device_id", "TEXT"),
        ("metadata_json", "TEXT NOT NULL"), ("created_at", "TEXT NOT NULL"),
    ], []),
}

BASELINE_INDEXES = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_firebase_uid ON users(firebase_uid) WHERE firebase_uid IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_sessions_user_expires ON auth_sessions(user_id,expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_manual_refresh_active ON manual_refresh_requests(user_id,status,requested_at)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_content_ingestion ON content_ingestion_runs(status) WHERE status='RUNNING'",
    "CREATE INDEX IF NOT EXISTS idx_content_taxonomy_node ON content_taxonomy(taxonomy_id,score)",
    "CREATE INDEX IF NOT EXISTS idx_content_published ON indexed_content(published_at)",
    "CREATE INDEX IF NOT EXISTS idx_content_event_published ON indexed_content(event_id,published_at)",
    "CREATE INDEX IF NOT EXISTS idx_enrichment_lookup ON content_enrichment(content_id,content_hash,output_language)",
]


def render_column(declaration, dialect):
    if declaration == "AUTO":
        return ("BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY" if dialect == POSTGRES
                else "INTEGER PRIMARY KEY AUTOINCREMENT")
    if dialect == POSTGRES:
        words = declaration.split(" ", 1)
        kind = {"INTEGER": "BIGINT", "REAL": "DOUBLE PRECISION"}.get(words[0], words[0])
        return kind + (" " + words[1] if len(words) > 1 else "")
    return declaration


def create_table_sql(name, dialect):
    columns, constraints = BASELINE_TABLES[name]
    body = [f"{column} {render_column(declaration, dialect)}" for column, declaration in columns] + constraints
    return f"CREATE TABLE IF NOT EXISTS {name}({','.join(body)})"


_now = now_iso


def _baseline(db):
    for name in BASELINE_TABLES:
        db.execute(create_table_sql(name, db.dialect))
        # Databases created by the old ad-hoc schema code may predate later columns.
        existing = set(db.table_columns(name))
        for column, declaration in BASELINE_TABLES[name][0]:
            if column not in existing:
                db.execute(f"ALTER TABLE {name} ADD COLUMN {column} {render_column(declaration, db.dialect)}")
    for statement in BASELINE_INDEXES:
        db.execute(statement)
    db.execute("INSERT INTO content_index_state(key,value,updated_at) VALUES('content_revision','0',?) ON CONFLICT(key) DO NOTHING", (_now(),))
    # One-time repairs that the old schema code re-ran at every start.
    db.execute("UPDATE indexed_content SET first_seen_at=COALESCE(first_seen_at,indexed_at),last_seen_at=COALESCE(last_seen_at,indexed_at),"
               "ingested_at=COALESCE(ingested_at,indexed_at) WHERE first_seen_at IS NULL OR last_seen_at IS NULL OR ingested_at IS NULL")
    db.execute("UPDATE user_briefing_deliveries SET status='CONTENT_READY',audio_status='PENDING',generation_stage='AUDIO_QUEUED',"
               "generation_started_at=COALESCE(generation_started_at,created_at),generation_updated_at=COALESCE(generation_updated_at,created_at) "
               "WHERE status='READY' AND audio_artifact_id IS NULL")
    if db.dialect == SQLITE:
        # Older SQLite importers substituted the collection time for a missing publication date.
        cutoff = iso(datetime.now(timezone.utc) - timedelta(days=1))
        db.execute("UPDATE indexed_content SET published_at=NULL WHERE published_at IS NOT NULL AND indexed_at IS NOT NULL "
                   "AND datetime(indexed_at)<datetime(?) AND ABS((julianday(published_at)-julianday(indexed_at))*86400)<1", (cutoff,))


def _hot_path_indexes(db):
    """Indexes for the queries every worker cycle and most API requests run."""
    for statement in (
        "CREATE INDEX IF NOT EXISTS idx_generation_jobs_queue ON generation_jobs(status,scheduled_for)",
        "CREATE INDEX IF NOT EXISTS idx_audio_jobs_queue ON audio_generation_jobs(status,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_notification_jobs_queue ON notification_jobs(status,scheduled_for)",
        "CREATE INDEX IF NOT EXISTS idx_notification_jobs_device ON notification_jobs(device_id,status)",
        "CREATE INDEX IF NOT EXISTS idx_push_devices_user ON push_devices(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_saved_stories_user_saved ON saved_stories(user_id,saved_at)",
        "CREATE INDEX IF NOT EXISTS idx_deliveries_edition_voice ON user_briefing_deliveries(edition_id,selected_voice_id)",
        "CREATE INDEX IF NOT EXISTS idx_edition_items_edition ON briefing_edition_items(edition_id,position)",
        "CREATE INDEX IF NOT EXISTS idx_script_segments_script ON audio_script_segments(audio_script_id,position)",
        "CREATE INDEX IF NOT EXISTS idx_manual_refresh_queue ON manual_refresh_requests(status,requested_at)",
        "CREATE INDEX IF NOT EXISTS idx_listening_progress_user ON briefing_listening_progress(user_id)",
    ):
        db.execute(statement)


def _article_search(db):
    """Accent-insensitive full-text search over article titles and descriptions."""
    if db.dialect == POSTGRES:
        from .search import PG_SEARCH_DOCUMENT
        db.execute(f"CREATE INDEX IF NOT EXISTS idx_content_search ON indexed_content USING GIN ({PG_SEARCH_DOCUMENT})")
        return
    db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS content_search USING fts5(title, description, content='indexed_content', "
               "content_rowid='rowid', tokenize='unicode61 remove_diacritics 2')")
    db.execute("CREATE TRIGGER IF NOT EXISTS content_search_insert AFTER INSERT ON indexed_content BEGIN "
               "INSERT INTO content_search(rowid,title,description) VALUES(new.rowid,new.title,new.description); END")
    db.execute("CREATE TRIGGER IF NOT EXISTS content_search_delete AFTER DELETE ON indexed_content BEGIN "
               "INSERT INTO content_search(content_search,rowid,title,description) VALUES('delete',old.rowid,old.title,old.description); END")
    db.execute("CREATE TRIGGER IF NOT EXISTS content_search_update AFTER UPDATE OF title,description ON indexed_content BEGIN "
               "INSERT INTO content_search(content_search,rowid,title,description) VALUES('delete',old.rowid,old.title,old.description); "
               "INSERT INTO content_search(rowid,title,description) VALUES(new.rowid,new.title,new.description); END")
    db.execute("INSERT INTO content_search(content_search) VALUES('rebuild')")


def _timestamp_columns(table):
    return [name for name, _ in BASELINE_TABLES[table][0] if name.endswith("_at") or name == "scheduled_for"]


def _canonical_timestamps(db):
    """Rewrite stored timestamps to the single format of timeutil.iso().

    Rows written before it mixed ``...Z`` (seconds) and ``...+00:00`` (microseconds); SQL compares
    these columns as text, which is only correct when every value has the same shape.
    """
    from .timeutil import normalize
    db.execute("CREATE TEMPORARY TABLE timestamp_rewrites(old TEXT PRIMARY KEY, new TEXT NOT NULL)")
    for table in BASELINE_TABLES:
        for column in _timestamp_columns(table):
            values = [row[0] for row in db.execute(f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL")]
            changes = [(value, normalize(value)) for value in values if normalize(value) != value]
            if not changes:
                continue
            db.execute("DELETE FROM timestamp_rewrites")
            db.executemany("INSERT INTO timestamp_rewrites(old,new) VALUES(?,?)", changes)
            # One pass per column; the lookup table is indexed, the target column usually is not.
            db.execute(f"UPDATE {table} SET {column}=(SELECT new FROM timestamp_rewrites WHERE old={table}.{column}) "
                       f"WHERE {column} IN (SELECT old FROM timestamp_rewrites)")
    db.execute("DROP TABLE timestamp_rewrites")
    row = db.execute("SELECT value FROM content_index_state WHERE key='retention_last_run'").fetchone()
    if row and normalize(row[0]) != row[0]:
        db.execute("UPDATE content_index_state SET value=? WHERE key='retention_last_run'", (normalize(row[0]),))


def _worker_heartbeats_and_push_payloads(db):
    """Worker liveness for /health/worker, and per-job push content for breaking news."""
    db.execute("CREATE TABLE IF NOT EXISTS worker_heartbeats(worker_id TEXT PRIMARY KEY, roles TEXT NOT NULL, started_at TEXT NOT NULL, "
               f"last_cycle_at TEXT NOT NULL, last_success_at TEXT, last_error TEXT, cycle_ms {render_column('INTEGER', db.dialect)}, "
               f"cycles {render_column('INTEGER NOT NULL DEFAULT 0', db.dialect)})")
    if "payload_json" not in set(db.table_columns("notification_jobs")):
        db.execute("ALTER TABLE notification_jobs ADD COLUMN payload_json TEXT")
    db.execute("CREATE INDEX IF NOT EXISTS idx_notification_jobs_user_type ON notification_jobs(user_id,notification_type,created_at)")


def _subscriptions(db):
    """Premium plans bought in the store; one row per user, written by the billing webhook."""
    db.execute("CREATE TABLE IF NOT EXISTS subscriptions(user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, "
               "period TEXT NOT NULL, status TEXT NOT NULL, store TEXT NOT NULL, product_id TEXT, purchase_token TEXT, "
               f"started_at TEXT, expires_at TEXT NOT NULL, auto_renew {render_column('INTEGER NOT NULL DEFAULT 1', db.dialect)}, "
               "updated_at TEXT NOT NULL)")


def _per_user_editions(db):
    """Each user gets an edition composed at their own briefing time (editions were shared by profile)."""
    if "user_id" not in set(db.table_columns("briefing_editions")):
        db.execute("ALTER TABLE briefing_editions ADD COLUMN user_id TEXT")
    db.execute("CREATE INDEX IF NOT EXISTS idx_briefing_editions_user ON briefing_editions(user_id,edition_date)")


MIGRATIONS = [
    ("0001_baseline", _baseline),
    ("0002_hot_path_indexes", _hot_path_indexes),
    ("0003_article_search", _article_search),
    ("0004_canonical_timestamps", _canonical_timestamps),
    ("0005_worker_heartbeats_and_push_payloads", _worker_heartbeats_and_push_payloads),
    ("0006_subscriptions", _subscriptions),
    ("0007_per_user_editions", _per_user_editions),
]


def migrate(db, migrations=None):
    """Apply pending migrations; safe to call concurrently from the API and the workers."""
    migrations = MIGRATIONS if migrations is None else migrations
    db.execute("CREATE TABLE IF NOT EXISTS schema_versions(id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    db.commit()
    applied = {row[0] for row in db.execute("SELECT id FROM schema_versions")}
    if all(name in applied for name, _ in migrations):
        db.rollback(); return []
    db.begin_immediate()
    try:
        # Re-read under the lock: another process may have migrated meanwhile.
        applied = {row[0] for row in db.execute("SELECT id FROM schema_versions")}
        done = []
        for name, step in migrations:
            if name in applied: continue
            step(db)
            db.execute("INSERT INTO schema_versions(id,applied_at) VALUES(?,?)", (name, _now()))
            done.append(name)
        db.commit()
        return done
    except Exception:
        db.rollback(); raise
