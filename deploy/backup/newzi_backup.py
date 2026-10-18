"""Daily backup of the product database (users, preferences, notifications, briefings).

Uses SQLite's online backup API, so the copy is consistent while the API and worker keep writing.
Each copy is integrity-checked before it is kept, compressed, and only the newest
NEWZI_BACKUP_KEEP copies stay on disk. With NEWZI_BACKUP_REMOTE set (an rclone destination such as
"gdrive:newzi-backups"), every copy is also uploaded off the server and remote copies older than
NEWZI_BACKUP_REMOTE_DAYS are removed. Exits non-zero on any failure, so systemd marks the run failed.

Standard library only; runs with the system python3.
"""
import gzip
import os
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////var/lib/newzi/product_backend.sqlite3")
BACKUP_DIR = Path(os.getenv("NEWZI_BACKUP_DIR", "/var/backups/newzi"))
KEEP = int(os.getenv("NEWZI_BACKUP_KEEP", "14"))
REMOTE = os.getenv("NEWZI_BACKUP_REMOTE", "").strip()
REMOTE_DAYS = int(os.getenv("NEWZI_BACKUP_REMOTE_DAYS", "30"))
PREFIX = "product_backend-"


def database_path():
    if not DATABASE_URL.startswith("sqlite:///"):
        sys.exit(f"backup: DATABASE_URL is not SQLite ({DATABASE_URL.split(':', 1)[0]}); back it up with its own tools")
    return Path(DATABASE_URL[len("sqlite:///"):])


def snapshot(source, target):
    # closing(): a sqlite3 connection used as a context manager only commits, it stays open.
    with closing(sqlite3.connect(f"file:{source}?mode=ro", uri=True)) as live, closing(sqlite3.connect(target)) as copy:
        live.backup(copy)
    with closing(sqlite3.connect(target)) as copy:
        result = copy.execute("PRAGMA integrity_check").fetchone()[0]
        users = copy.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if result != "ok":
        raise RuntimeError(f"integrity check failed: {result}")
    return users


def main():
    source = database_path()
    if not source.exists():
        sys.exit(f"backup: database not found at {source}")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    raw = BACKUP_DIR / f"{PREFIX}{stamp}.sqlite3"
    final = raw.with_name(raw.name + ".gz")
    try:
        users = snapshot(source, raw)
        with open(raw, "rb") as plain, gzip.open(final, "wb", compresslevel=6) as packed:
            shutil.copyfileobj(plain, packed)
    finally:
        raw.unlink(missing_ok=True)
    os.chmod(final, 0o600)
    print(f"backup: {final} ({final.stat().st_size / 1e6:.1f} MB, {users} users)")
    copies = sorted(BACKUP_DIR.glob(f"{PREFIX}*.sqlite3.gz"))
    for old in copies[:-KEEP] if KEEP > 0 else []:
        old.unlink()
        print(f"backup: removed {old.name}")
    if REMOTE:
        subprocess.run(["rclone", "copy", str(final), REMOTE], check=True)
        subprocess.run(["rclone", "delete", REMOTE, "--min-age", f"{REMOTE_DAYS}d", "--include", f"{PREFIX}*.sqlite3.gz"], check=True)
        print(f"backup: uploaded to {REMOTE}")
    else:
        print("backup: NEWZI_BACKUP_REMOTE not set; the copy stays on this server only")


if __name__ == "__main__":
    main()
