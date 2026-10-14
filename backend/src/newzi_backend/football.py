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

    def overview(self, now=None):
        """Games being played now and the next ones, across every covered competition, soonest first."""
        now = now or datetime.now(timezone.utc)
        since, until = (now - timedelta(days=1)).date().isoformat(), (now + timedelta(days=WINDOW_DAYS - 1)).date().isoformat()
        # While a game is on, scores are refreshed every minute; otherwise every ten.
        live_ttl = lambda cached: LIVE_MATCHES_TTL if cached and any(match.get("status") in LIVE for match in cached) else MATCHES_TTL
        matches = self._cached("matches", live_ttl, lambda: self.fetch("/matches", {"dateFrom": since, "dateTo": until}).get("matches", []))
        matches = sorted((match for match in matches if _kickoff(match)), key=_kickoff)
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

    def standings(self, code):
        """A competition's table (several groups for cup group stages), refreshed hourly."""
        data = self._cached(f"standings:{code}", STANDINGS_TTL, lambda: self.fetch(f"/competitions/{code}/standings"))
        groups = [{"name": _group_name(group.get("group")), "rows": [_row(row) for row in group.get("table", [])]}
                  for group in data.get("standings", []) if group.get("type") == "TOTAL" and group.get("table")]
        return {"available": True, "competition": _competition({**(data.get("competition") or {}), "code": code}),
                "matchday": (data.get("season") or {}).get("currentMatchday"), "groups": groups}


def _group_name(group):
    # "GROUP_A" -> "Grupo A"; league tables have no group.
    return f"Grupo {group.split('_')[-1]}" if group else None


def _competition(competition):
    code = (competition or {}).get("code")
    return {"code": code, "name": COMPETITIONS.get(code) or (competition or {}).get("name") or code}


def _row(row):
    team = row.get("team")
    return {"position": row.get("position"), "team": _team(team), "tla": _tla(team), "played": row.get("playedGames"),
            "won": row.get("won"), "draw": row.get("draw"), "lost": row.get("lost"),
            "goal_difference": row.get("goalDifference"), "points": row.get("points")}


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
            "home_tla": _tla(match.get("homeTeam")), "away_tla": _tla(match.get("awayTeam")),
            "home_goals": full.get("home"), "away_goals": full.get("away")}


def follows_football(prefs):
    if (prefs or {}).get("content_scope") == "all":
        return True
    # Sports as a whole, football, or anything inside football (Brasileirão, Libertadores...); not Formula 1.
    registry = taxonomy()
    return any(code in FOLLOWED_BY or "FUTEBOL" in registry.ancestors(code) for code in (prefs or {}).get("topics") or [])


_service = FootballService()


def football_for(prefs, require_follow=True):
    """Football data for a user: unavailable without a key; by default only for football followers,
    the Explore card (``require_follow=False``) for everyone."""
    if not FootballService.configured():
        return {"available": False, "reason": "NOT_CONFIGURED"}
    if require_follow and not follows_football(prefs):
        return {"available": False, "reason": "NOT_FOLLOWED"}
    try:
        return _service.overview()
    except Exception:
        return {"available": False, "reason": "PROVIDER_UNAVAILABLE"}


def football_standings(code):
    code = (code or "").upper()
    if not FootballService.configured():
        return {"available": False, "reason": "NOT_CONFIGURED"}
    if code not in COMPETITIONS or code in WITHOUT_TABLE:
        return {"available": False, "reason": "UNKNOWN_COMPETITION"}
    try:
        return _service.standings(code)
    except Exception:
        return {"available": False, "reason": "PROVIDER_UNAVAILABLE"}
