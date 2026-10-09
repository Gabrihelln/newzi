"""Load the repository-root .env file into the process environment."""
import os

from .paths import PROJECT_ROOT


def load_local_environment(env_path=None):
    """Read simple KEY=VALUE lines without overriding variables already set in the process."""
    env_path = env_path or PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip(); value = value.strip().strip('"').strip("'")
        if key == "GOOGLE_APPLICATION_CREDENTIALS" and value and not os.path.isabs(value):
            value = str((PROJECT_ROOT / value).resolve())
        if key:
            os.environ.setdefault(key, value)
