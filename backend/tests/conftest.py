import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import support  # noqa: E402  (configures the isolated test environment before any backend import)


@pytest.fixture()
def repo():
    """A migrated, empty product database (PostgreSQL when TEST_DATABASE_URL is set)."""
    database_url = os.getenv("TEST_DATABASE_URL")
    support.fresh_environment(database_url)
    if database_url:
        support.reset_postgres(database_url)
    from newzi_backend.product_backend import ProductRepository
    repository = ProductRepository()
    yield repository
    repository.close_thread_connection()


def add_user(repo, uid, timezone="UTC", briefing_time="06:00", topics=("TECHNOLOGY",)):
    import json
    repo.db.execute("INSERT INTO users(id,email,display_name,language,timezone,created_at,updated_at,status) VALUES(?,?,?,?,?,?,?,?)",
                    (uid, uid + "@x", uid, "pt-BR", timezone, "t", "t", "ACTIVE"))
    repo.db.execute("""INSERT INTO user_preferences(user_id,topics_json,language,country_scope,briefing_time,timezone,briefing_size,audio_enabled,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?)""", (uid, json.dumps(list(topics)), "pt-BR", "BOTH", briefing_time, timezone, 10, 0, "t"))
    repo.db.commit()
