"""Post-match audio summary (Premium): a short narrated wrap-up of a finished game.

When the ``football`` worker sees a game end (football_alerts.py) and a Premium fan follows it, the game is
queued here; the same worker narrates it on its next cycles (one TTS call, about a minute of audio) with the
final score, the competition and round, each side's place in the table when there is one, and up to two recent
headlines about the game. One file per game serves every fan; files live in ``<audio root>/matches`` for
MATCH_AUDIO_DAYS days.
"""
import hashlib
import logging
import os
import re
import shutil
from datetime import timedelta
from pathlib import Path

from .timeutil import iso, utc_now

log = logging.getLogger(__name__)
MATCH_AUDIO_DAYS = int(os.getenv("MATCH_AUDIO_DAYS", "7"))


def _place(rows, team_id):
    row = next((row for row in rows if row.get("team_id") == team_id), None)
    return (row["position"], row["points"]) if row else None


def match_script(match, standings_rows=(), headlines=()):
    """What is narrated: result first, then the table and the news. ``match`` is football-data's raw game."""
    from .football import COMPETITIONS, _team
    home, away = _team(match.get("homeTeam")), _team(match.get("awayTeam"))
    full = (match.get("score") or {}).get("fullTime") or {}
    home_goals, away_goals = full.get("home") or 0, full.get("away") or 0
    code = (match.get("competition") or {}).get("code")
    competition = COMPETITIONS.get(code, (match.get("competition") or {}).get("name") or "")
    where = f"pelo {competition}" + (f", rodada {match['matchday']}" if match.get("matchday") else "") if competition else ""
    goals = lambda n: "um gol" if n == 1 else f"{n} gols" if n else "nenhum gol"
    parts = [f"Olá. Este é o resumo do jogo no Newzi. Fim de jogo {where}.".replace("  ", " ").replace(" .", ".")]
    if home_goals == away_goals:
        parts.append(f"{home} e {away} empataram em {home_goals} a {away_goals}.")
    else:
        winner, loser = (home, away) if home_goals > away_goals else (away, home)
        high, low = max(home_goals, away_goals), min(home_goals, away_goals)
        parts.append(f"{winner} venceu {loser} por {high} a {low}.")
    parts.append(f"{home} marcou {goals(home_goals)}, e {away}, {goals(away_goals)}.")
    for side, name in (("homeTeam", home), ("awayTeam", away)):
        place = _place(standings_rows, (match.get(side) or {}).get("id"))
        if place:
            parts.append(f"Na tabela, {name} está em {place[0]}º lugar, com {place[1]} pontos.")
    told = 0
    for headline in headlines:
        text = re.sub(r"\s+", " ", headline or "").strip(" .")
        if text and told < 2:
            parts.append(("Nas notícias: " if not told else "E mais: ") + text + ".")
            told += 1
    parts.append("Esse foi o resumo do jogo. Até a próxima.")
    return " ".join(parts)


def queue(repo, match, standings_rows=(), headlines=(), now=None):
    """Queue a finished game's audio once (a game seen finishing twice keeps its first summary)."""
    now = now or utc_now()
    script = match_script(match, standings_rows, headlines)
    cursor = repo.db.execute("""INSERT INTO football_match_audio(match_id,status,script,created_at,updated_at) VALUES(?,'PENDING',?,?,?)
        ON CONFLICT(match_id) DO NOTHING""", (match["id"], script, iso(now), iso(now)))
    repo.db.commit()
    return cursor.rowcount == 1


def generate_pending(repo, audio_service=None, limit=2):
    """Narrate up to ``limit`` queued games; returns how many became READY."""
    rows = repo.db.execute("SELECT * FROM football_match_audio WHERE status='PENDING' ORDER BY created_at LIMIT ?", (limit,)).fetchall()
    if not rows:
        return 0
    from .audio import AudioService
    audio = audio_service or AudioService(repo)
    voice = audio.default_voice("pt-BR")
    ready = 0
    for row in rows:
        claimed = repo.db.execute("UPDATE football_match_audio SET status='GENERATING',updated_at=? WHERE match_id=? AND status='PENDING'",
                                  (iso(utc_now()), row["match_id"])).rowcount
        repo.db.commit()
        if not claimed:
            continue
        try:
            result = audio.provider.synthesize(row["script"], audio._provider_voice(voice, "pt-BR"), "pt-BR")
            source = Path(result["path"])
            folder = audio.storage.root / "matches"; folder.mkdir(parents=True, exist_ok=True)
            destination = folder / f"{row['match_id']}{source.suffix.lower() or '.mp3'}"
            shutil.copyfile(source, destination); source.unlink(missing_ok=True)
            repo.db.execute("""UPDATE football_match_audio SET status='READY',storage_path=?,mime_type=?,duration_ms=?,error=NULL,updated_at=?
                WHERE match_id=?""", (str(destination), result.get("mime_type") or "audio/mpeg", int(result.get("duration_ms") or 0), iso(utc_now()), row["match_id"]))
            ready += 1
        except Exception as exc:
            log.warning("match audio %s failed: %s", row["match_id"], exc)
            repo.db.execute("UPDATE football_match_audio SET status='FAILED',error=?,updated_at=? WHERE match_id=?",
                            (str(exc)[:300], iso(utc_now()), row["match_id"]))
        repo.db.commit()
    return ready


def match_audio(repo, uid, match_id):
    """The game's audio for the app: status and, when READY, where to stream it (Premium)."""
    from .subscriptions import require
    require(repo, uid, "match_audio")
    row = repo.db.execute("SELECT * FROM football_match_audio WHERE match_id=?", (match_id,)).fetchone()
    if not row:
        return {"match_id": match_id, "status": "NOT_AVAILABLE"}
    out = {"match_id": match_id, "status": row["status"], "duration_ms": row["duration_ms"]}
    if row["status"] == "READY":
        version = hashlib.sha256((row["updated_at"] or "").encode()).hexdigest()[:10]
        out["audio_url"] = f"/api/v1/me/football/matches/{match_id}/audio/file?v={version}"
    return out


def match_audio_file(repo, uid, match_id, storage_root):
    from .product_backend import not_found
    from .subscriptions import require
    require(repo, uid, "match_audio")
    row = repo.db.execute("SELECT storage_path,mime_type FROM football_match_audio WHERE match_id=? AND status='READY'", (match_id,)).fetchone()
    path = Path(row["storage_path"]).resolve() if row and row["storage_path"] else None
    if not path or Path(storage_root).resolve() not in path.parents or not path.is_file():
        raise not_found("match audio not available")
    return path, row["mime_type"] or "audio/mpeg"


def purge_old(repo, now=None):
    """Retention: games older than MATCH_AUDIO_DAYS lose their audio."""
    cutoff = iso((now or utc_now()) - timedelta(days=MATCH_AUDIO_DAYS))
    removed = 0
    for row in repo.db.execute("SELECT match_id,storage_path FROM football_match_audio WHERE created_at<?", (cutoff,)).fetchall():
        if row["storage_path"]:
            Path(row["storage_path"]).unlink(missing_ok=True)
        repo.db.execute("DELETE FROM football_match_audio WHERE match_id=?", (row["match_id"],))
        removed += 1
    repo.db.commit()
    return {"match_audio_removed": removed}


def news_headlines(repo, match, now):
    """Recent football headlines naming both teams (the game's own coverage), newest first."""
    from .football import _team
    from .football_alerts import FOOTBALL_TOPICS, _fold, _name_pattern
    home, away = _name_pattern(_team(match.get("homeTeam"))), _name_pattern(_team(match.get("awayTeam")))
    marks = ",".join("?" for _ in FOOTBALL_TOPICS)
    rows = repo.db.execute(f"""SELECT DISTINCT c.title,c.published_at FROM indexed_content c JOIN content_taxonomy t ON t.content_id=c.id
        WHERE c.published_at>=? AND (t.taxonomy_id IN ({marks}) OR t.taxonomy_id LIKE 'FUTEBOL%') AND lower(COALESCE(c.source_language,'')) LIKE 'pt%'
        ORDER BY c.published_at DESC LIMIT 200""", (iso(now - timedelta(hours=4)), *FOOTBALL_TOPICS)).fetchall()
    return [row["title"] for row in rows if home.search(_fold(row["title"])) and away.search(_fold(row["title"]))][:2]

