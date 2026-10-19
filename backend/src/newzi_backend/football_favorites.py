"""Favourite teams, followed games, team alerts and the cached team crests (Esportes › Times favoritos).

A person picks favourite teams (Básico: 1; Premium: more, once purchases exist) and which alerts they want:
kickoff, goals, final result and news about the team. A single game can also be followed with its bell.
The alerts themselves are sent by the ``football`` worker role (football_alerts.py).
"""
import io
import json
import os
from pathlib import Path

from .football import COMPETITIONS, CREST_VERSION, crest_path, ensure_competition_teams
from .paths import BACKEND_DATA
from .timeutil import now_iso

ALERT_FIELDS = {"kickoff": "team_kickoff_enabled", "goals": "team_goals_enabled", "final": "team_final_enabled", "news": "team_news_enabled",
                "reminder": "team_reminder_enabled", "live_activities": "live_activities_enabled"}
CREST_SIZE = 128


class FavoritesError(ValueError):
    """A request the user can fix (unknown team, over the plan's limit)."""
    def __init__(self, code, message):
        super().__init__(message); self.code = code


def crest_root():
    """FOOTBALL_CREST_ROOT, else next to the audio storage (writable on the server), else backend/data."""
    explicit = os.getenv("FOOTBALL_CREST_ROOT")
    if explicit:
        return Path(explicit)
    audio = os.getenv("AUDIO_STORAGE_ROOT")
    return Path(audio).parent / "football-crests" if audio else BACKEND_DATA / "football-crests"


def crest_file(repo, team_id, download=None):
    """The team's official crest, downloaded once from the provider, checked, resized and kept on disk.

    The provider's images come in different sizes (70 and 200 px) and margins: the transparent margin is cut and
    the crest is scaled, up or down, to fill the same square, so every crest looks the same size in the app."""
    path = crest_root() / f"{int(team_id)}.v{CREST_VERSION}.png"
    if path.is_file():
        return path
    row = repo.db.execute("SELECT crest_url FROM football_teams WHERE id=?", (int(team_id),)).fetchone()
    if not row or not row["crest_url"] or not str(row["crest_url"]).startswith("https://"):
        return None
    from PIL import Image
    try:
        raw = (download or _download)(row["crest_url"])
        with Image.open(io.BytesIO(raw)) as source:
            image = source.convert("RGBA")
    except Exception:
        return None
    box = image.getchannel("A").getbbox()
    if box:
        image = image.crop(box)
    scale = CREST_SIZE / max(image.width, image.height)
    image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", (CREST_SIZE, CREST_SIZE), (0, 0, 0, 0))
    canvas.alpha_composite(image, ((CREST_SIZE - image.width) // 2, (CREST_SIZE - image.height) // 2))
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    canvas.save(temp, "PNG", optimize=True)
    temp.replace(path)
    return path


def _download(url):
    import httpx
    response = httpx.get(url, timeout=httpx.Timeout(8.0, connect=3.0), follow_redirects=True)
    response.raise_for_status()
    if len(response.content) > 2_000_000:
        raise ValueError("crest too large")
    return response.content


def _team_out(row):
    codes = json.loads(row["competitions"] or "[]")
    return {"id": row["id"], "name": row["name"], "tla": row["tla"], "crest": crest_path({"id": row["id"], "crest": row["crest_url"]}),
            "competitions": [{"code": code, "name": COMPETITIONS.get(code, code)} for code in codes if code in COMPETITIONS]}


def favorite_limit(repo, uid):
    from .subscriptions import limit
    return limit(repo, uid, "favorite_teams")


def favorites(repo, uid):
    from .notifications import NotificationService
    rows = repo.db.execute("""SELECT t.* FROM user_favorite_teams f JOIN football_teams t ON t.id=f.team_id
        WHERE f.user_id=? ORDER BY f.position,f.created_at""", (uid,)).fetchall()
    settings = NotificationService(repo).settings(uid)
    followed = [row["match_id"] for row in repo.db.execute("SELECT match_id FROM user_followed_matches WHERE user_id=?", (uid,))]
    return {"teams": [_team_out(row) for row in rows], "limit": favorite_limit(repo, uid),
            "alerts": {key: settings[field] for key, field in ALERT_FIELDS.items()}, "followed_matches": followed}


def save_favorites(repo, uid, data):
    """Replace the favourite teams (in the given order) and, when sent, the team alert switches."""
    from .notifications import NotificationService
    data = data or {}
    if "team_ids" in data:
        ids = []
        for value in data.get("team_ids") or []:
            if isinstance(value, bool) or not isinstance(value, int):
                raise FavoritesError("VALIDATION_ERROR", "team_ids must be integers")
            if value not in ids:
                ids.append(value)
        limit = favorite_limit(repo, uid)
        if len(ids) > limit:
            raise FavoritesError("FAVORITES_LIMIT", f"your plan allows {limit} favourite team(s)")
        known = {row["id"] for row in repo.db.execute(f"SELECT id FROM football_teams WHERE id IN ({','.join('?' for _ in ids) or 'NULL'})", ids)}
        if set(ids) - known:
            raise FavoritesError("VALIDATION_ERROR", "unknown team")
        repo.db.execute("DELETE FROM user_favorite_teams WHERE user_id=?", (uid,))
        repo.db.executemany("INSERT INTO user_favorite_teams(user_id,team_id,position,created_at) VALUES(?,?,?,?)",
                            [(uid, team_id, index, now_iso()) for index, team_id in enumerate(ids)])
        repo.db.commit()
    alerts = data.get("alerts")
    if isinstance(alerts, dict):
        changes = {ALERT_FIELDS[key]: value for key, value in alerts.items() if key in ALERT_FIELDS}
        if any(not isinstance(value, bool) for value in changes.values()):
            raise FavoritesError("VALIDATION_ERROR", "alerts must be true or false")
        if changes:
            NotificationService(repo).save_settings(uid, changes)
    return favorites(repo, uid)


def follow_match(repo, uid, match_id, following):
    """The bell of one game: its kickoff, goals and final result reach this person even without a favourite team in it."""
    if following:
        repo.db.execute("INSERT INTO user_followed_matches(user_id,match_id,created_at) VALUES(?,?,?) ON CONFLICT DO NOTHING", (uid, int(match_id), now_iso()))
    else:
        repo.db.execute("DELETE FROM user_followed_matches WHERE user_id=? AND match_id=?", (uid, int(match_id)))
    repo.db.commit()
    return {"match_id": int(match_id), "following": bool(following)}


def search_teams(repo, query="", competition=""):
    """Teams of a competition (loaded on first use) or matching a name, for the favourites grid and search."""
    competition = (competition or "").upper()
    if competition:
        ensure_competition_teams(competition, repo)
    rows = repo.db.execute("SELECT * FROM football_teams ORDER BY name").fetchall()
    needle = _fold(query or "")
    out = []
    for row in rows:
        codes = json.loads(row["competitions"] or "[]")
        if competition and competition not in codes:
            continue
        if needle and needle not in _fold(f"{row['name']} {row['tla']}"):
            continue
        out.append(_team_out(row))
    return {"teams": out[:80]}


def _fold(value):
    import unicodedata
    return "".join(ch for ch in unicodedata.normalize("NFD", value.lower()) if unicodedata.category(ch) != "Mn")
