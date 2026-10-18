"""World football fixtures and league tables from football-data.org (free tier: 10 calls/minute).

Set FOOTBALL_DATA_TOKEN (a free key from football-data.org) to enable it; without a key the feature is
simply unavailable. One call lists the next days' games of every competition the plan covers (Brasileirão,
Libertadores, the big European leagues, Champions League...); each table is fetched only when someone opens
it. Responses are cached in memory and the last good answer is served when the API fails, so the app never
waits on, or hammers, the provider.
"""
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx

from newzi_engine.topic_registry import taxonomy

log = logging.getLogger(__name__)
BASE_URL = "https://api.football-data.org/v4"
MATCHES_TTL, LIVE_MATCHES_TTL, STANDINGS_TTL = 600, 60, 3600
WINDOW_DAYS = 9                       # the provider accepts at most a 10-day range
UPCOMING_LIMIT = 150
LIVE = {"IN_PLAY", "PAUSED"}
UPCOMING = {"SCHEDULED", "TIMED"}
FOLLOWED_BY = ("SPORTS", "FUTEBOL", "BRASILEIRAO")
# Display names, in the order competitions are offered in the app (Brazilian ones first).
COMPETITIONS = {"BSA": "Brasileirão", "CLI": "Libertadores", "CL": "Champions League", "PL": "Premier League",
                "PD": "La Liga", "SA": "Serie A", "BL1": "Bundesliga", "FL1": "Ligue 1", "PPL": "Liga Portugal",
                "DED": "Eredivisie", "ELC": "Championship", "WC": "Copa do Mundo", "EC": "Eurocopa"}
WITHOUT_TABLE = {"CLI"}             # the free plan has Libertadores games but not its table
# Brasileirão table zones (2026 rules): coloured strip next to the position.
ZONES = {"BSA": [((1, 4), "libertadores"), ((5, 6), "pre_libertadores"), ((7, 12), "sul_americana"), ((17, 20), "relegation")]}
SEASON_TTL, LIVE_SEASON_TTL = 3600, 120


def http_fetch(path, params=None):
    token = os.getenv("FOOTBALL_DATA_TOKEN", "").strip()
    response = httpx.get(BASE_URL + path, params=params, headers={"X-Auth-Token": token}, timeout=httpx.Timeout(8.0, connect=3.0))
    response.raise_for_status()
    return response.json()


def _kickoff(match):
    try:
        return datetime.fromisoformat((match.get("utcDate") or "").replace("Z", "+00:00"))
    except ValueError:
        return None


class FootballService:
    def __init__(self, fetch=http_fetch, clock=time.monotonic):
        self.fetch, self.clock = fetch, clock
        self._cache = {}
        self._lock = threading.Lock()

    @staticmethod
    def configured():
        return bool(os.getenv("FOOTBALL_DATA_TOKEN", "").strip())

    def _cached(self, key, ttl, loader):
        with self._lock:
            hit = self._cache.get(key)
            if callable(ttl): ttl = ttl(hit[1] if hit else None)
            if hit and self.clock() - hit[0] < ttl:
                return hit[1]
        try:
            value = loader()
        except Exception as exc:  # network, rate limit, plan without this competition...
            log.warning("football-data %s failed: %s", key, exc)
            if hit: return hit[1]
            raise
        with self._lock:
            self._cache[key] = (self.clock(), value)
        return value

    def raw_matches(self, now=None):
        """Every game from yesterday to the next days, finished ones included (the alerts worker needs them)."""
        now = now or datetime.now(timezone.utc)
        since, until = (now - timedelta(days=1)).date().isoformat(), (now + timedelta(days=WINDOW_DAYS - 1)).date().isoformat()
        # While a game is on, scores are refreshed every minute; otherwise every ten.
        live_ttl = lambda cached: LIVE_MATCHES_TTL if cached and any(match.get("status") in LIVE for match in cached) else MATCHES_TTL
        return self._cached("matches", live_ttl, lambda: self.fetch("/matches", {"dateFrom": since, "dateTo": until}).get("matches", []))

    def overview(self, now=None):
        """Games being played now and the next ones, across every covered competition, soonest first."""
        now = now or datetime.now(timezone.utc)
        matches = sorted((match for match in self.raw_matches(now) if _kickoff(match)), key=_kickoff)
        live = [match for match in matches if match.get("status") in LIVE]
        # A game whose kickoff passed hours ago but still says "scheduled" was postponed or is stale: skip it.
        upcoming = [match for match in matches if match.get("status") in UPCOMING and _kickoff(match) >= now - timedelta(hours=2)]
        present = {(match.get("competition") or {}).get("code") for match in live + upcoming}
        return {
            "available": True,
            "live": [_match(match) for match in live],
            "upcoming": [_match(match) for match in upcoming[:UPCOMING_LIMIT]],
            "competitions": [{"code": code, "name": name, "table": code not in WITHOUT_TABLE} for code, name in COMPETITIONS.items() if code in present],
        }

    def season_matches(self, code):
        """Every game of a competition's season (one call): rounds for the Jogos tab and each team's recent form."""
        ttl = lambda cached: LIVE_SEASON_TTL if cached and any(match.get("status") in LIVE for match in cached) else SEASON_TTL
        return self._cached(f"season:{code}", ttl, lambda: self.fetch(f"/competitions/{code}/matches").get("matches", []))

    def standings(self, code):
        """A competition's table (several groups for cup group stages), refreshed hourly.

        The free plan sends no recent form, so the last three results come from the season's finished games."""
        data = self._cached(f"standings:{code}", STANDINGS_TTL, lambda: self.fetch(f"/competitions/{code}/standings"))
        try:
            form = _recent_form(self.season_matches(code))
        except Exception:
            form = {}
        zones = ZONES.get(code, [])
        groups = [{"name": _group_name(group.get("group")), "rows": [_row(row, form, zones) for row in group.get("table", [])]}
                  for group in data.get("standings", []) if group.get("type") == "TOTAL" and group.get("table")]
        return {"available": True, "competition": _competition({**(data.get("competition") or {}), "code": code}),
                "season": ((data.get("season") or {}).get("startDate") or "")[:4] or None,
                "matchday": (data.get("season") or {}).get("currentMatchday"), "groups": groups}

    def round_games(self, code, matchday=None):
        """The games of one round (the current one by default) and how many rounds the season has."""
        matches = self.season_matches(code)
        rounds = sorted({match.get("matchday") for match in matches if match.get("matchday")})
        # The current round is the one of the next game to be played (or being played); a postponed game of an
        # old round does not pull it back.
        current = next((match.get("matchday") for match in sorted(matches, key=lambda m: _kickoff(m) or datetime.max.replace(tzinfo=timezone.utc))
                        if match.get("status") in UPCOMING | LIVE and match.get("matchday")), rounds[-1] if rounds else None)
        chosen = int(matchday) if matchday and int(matchday) in rounds else current
        games = sorted((match for match in matches if match.get("matchday") == chosen and _kickoff(match)), key=_kickoff)
        return {"available": True, "competition": _competition({"code": code}), "matchday": chosen, "current_matchday": current,
                "matchdays": rounds, "matches": [_match(match) for match in games]}


def _group_name(group):
    # "GROUP_A" -> "Grupo A"; league tables have no group.
    return f"Grupo {group.split('_')[-1]}" if group else None


def _competition(competition):
    code = (competition or {}).get("code")
    return {"code": code, "name": COMPETITIONS.get(code) or (competition or {}).get("name") or code}


def _row(row, form=None, zones=()):
    team = row.get("team") or {}
    position = row.get("position")
    zone = next((name for (first, last), name in zones if position and first <= position <= last), None)
    return {"position": position, "team": _team(team), "team_id": team.get("id"), "tla": _tla(team), "crest": crest_path(team),
            "played": row.get("playedGames"), "won": row.get("won"), "draw": row.get("draw"), "lost": row.get("lost"),
            "goal_difference": row.get("goalDifference"), "points": row.get("points"),
            "form": (form or {}).get(team.get("id"), []), "zone": zone}


def _recent_form(matches, last=3):
    """team id -> its last results, oldest first: "W" won, "D" drew, "L" lost."""
    results = {}
    for match in sorted((m for m in matches if m.get("status") == "FINISHED" and _kickoff(m)), key=_kickoff):
        full = (match.get("score") or {}).get("fullTime") or {}
        home, away = full.get("home"), full.get("away")
        if home is None or away is None:
            continue
        for side, mine, theirs in (("homeTeam", home, away), ("awayTeam", away, home)):
            team_id = (match.get(side) or {}).get("id")
            if team_id:
                results.setdefault(team_id, []).append("W" if mine > theirs else "D" if mine == theirs else "L")
    return {team_id: values[-last:] for team_id, values in results.items()}


# Bump to redraw every cached crest after a change in how they are drawn; the ?v= also refreshes the app's image cache.
CREST_VERSION = 2


def crest_path(team):
    """Our cached copy of the team's official crest (served by /api/v1/football/crests/{id}.png)."""
    team_id = (team or {}).get("id")
    return f"/api/v1/football/crests/{team_id}.png?v={CREST_VERSION}" if team_id and (team or {}).get("crest") else None


# The provider's short names for some Brazilian clubs are not how fans call them.
DISPLAY_NAMES = {"Paranaense": "Athletico-PR", "Mineiro": "Atlético-MG", "Vasco da Gama": "Vasco", "Clube do Remo": "Remo",
                 "Bragantino": "Red Bull Bragantino", "Goianiense": "Atlético-GO"}


def _team(team):
    team = team or {}
    name = team.get("shortName") or team.get("name") or team.get("tla") or "?"
    return DISPLAY_NAMES.get(name, name)


def _tla(team):
    """Three-letter code for the score badge; derived from the name when the provider has none."""
    team = team or {}
    return (team.get("tla") or _team(team).replace("-", "")[:3]).upper()


def _match(match):
    full = ((match.get("score") or {}).get("fullTime") or {})
    return {"id": match.get("id"), "kickoff": match.get("utcDate"), "status": match.get("status"), "matchday": match.get("matchday"),
            "competition": _competition(match.get("competition")),
            "home": _team(match.get("homeTeam")), "away": _team(match.get("awayTeam")),
            "home_id": (match.get("homeTeam") or {}).get("id"), "away_id": (match.get("awayTeam") or {}).get("id"),
            "home_crest": crest_path(match.get("homeTeam")), "away_crest": crest_path(match.get("awayTeam")),
            "home_tla": _tla(match.get("homeTeam")), "away_tla": _tla(match.get("awayTeam")),
            "home_goals": full.get("home"), "away_goals": full.get("away")}


def follows_football(prefs):
    if (prefs or {}).get("content_scope") == "all":
        return True
    # Sports as a whole, football, or anything inside football (Brasileirão, Libertadores...); not Formula 1.
    registry = taxonomy()
    return any(code in FOLLOWED_BY or "FUTEBOL" in registry.ancestors(code) for code in (prefs or {}).get("topics") or [])


_service = FootballService()


def remember_teams(repo, payload_teams):
    """Keep every team seen (name, code, crest, competitions) in ``football_teams``: the catalog behind
    "Times favoritos" and the crest cache. Only writes when something changed."""
    if repo is None:
        return
    from .timeutil import now_iso
    import json as _json
    for team, code in payload_teams:
        team_id = (team or {}).get("id")
        if not team_id:
            continue
        row = repo.db.execute("SELECT name,tla,crest_url,competitions FROM football_teams WHERE id=?", (team_id,)).fetchone()
        competitions = sorted(set(_json.loads(row["competitions"]) if row else []) | ({code} if code else set()))
        values = (_team(team), _tla(team), team.get("crest"), _json.dumps(competitions))
        if row and (row["name"], row["tla"], row["crest_url"], row["competitions"]) == values:
            continue
        repo.db.execute("""INSERT INTO football_teams(id,name,tla,crest_url,competitions,updated_at) VALUES(?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET name=excluded.name,tla=excluded.tla,crest_url=COALESCE(excluded.crest_url,football_teams.crest_url),
            competitions=excluded.competitions,updated_at=excluded.updated_at""", (team_id, *values, now_iso()))
    repo.db.commit()


def _teams_of_matches(matches):
    return [(match.get(side), (match.get("competition") or {}).get("code")) for match in matches for side in ("homeTeam", "awayTeam")]


def football_for(prefs, require_follow=True, repo=None):
    """Football data for a user: unavailable without a key; by default only for football followers,
    the Explore card (``require_follow=False``) for everyone."""
    if not FootballService.configured():
        return {"available": False, "reason": "NOT_CONFIGURED"}
    if require_follow and not follows_football(prefs):
        return {"available": False, "reason": "NOT_FOLLOWED"}
    try:
        overview = _service.overview()
        try:
            remember_teams(repo, _teams_of_matches(_service.raw_matches()))
        except Exception as exc:
            log.warning("football team catalog not updated: %s", exc)
        return overview
    except Exception:
        return {"available": False, "reason": "PROVIDER_UNAVAILABLE"}


def football_round(code, matchday=None, repo=None):
    code = (code or "").upper()
    if not FootballService.configured():
        return {"available": False, "reason": "NOT_CONFIGURED"}
    if code not in COMPETITIONS:
        return {"available": False, "reason": "UNKNOWN_COMPETITION"}
    try:
        result = _service.round_games(code, matchday)
        try:
            remember_teams(repo, _teams_of_matches(_service.season_matches(code)))
        except Exception as exc:
            log.warning("football team catalog not updated: %s", exc)
        return result
    except Exception:
        return {"available": False, "reason": "PROVIDER_UNAVAILABLE"}


def football_standings(code, repo=None):
    code = (code or "").upper()
    if not FootballService.configured():
        return {"available": False, "reason": "NOT_CONFIGURED"}
    if code not in COMPETITIONS or code in WITHOUT_TABLE:
        return {"available": False, "reason": "UNKNOWN_COMPETITION"}
    try:
        table = _service.standings(code)
        try:
            data = _service._cached(f"standings:{code}", STANDINGS_TTL, lambda: {})
            remember_teams(repo, [(row.get("team"), code) for group in data.get("standings", []) for row in group.get("table", [])])
        except Exception as exc:
            log.warning("football team catalog not updated: %s", exc)
        return table
    except Exception:
        return {"available": False, "reason": "PROVIDER_UNAVAILABLE"}


def ensure_competition_teams(code, repo):
    """Load a competition's teams into the catalog (its table, or its season's games for cups without one)."""
    code = (code or "").upper()
    if code not in COMPETITIONS or not FootballService.configured():
        return
    if code in WITHOUT_TABLE:
        football_round(code, repo=repo)
    else:
        football_standings(code, repo=repo)


def football_service():
    return _service
