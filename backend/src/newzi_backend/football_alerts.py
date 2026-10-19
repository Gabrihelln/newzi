"""Alerts for favourite teams and followed games: kickoff, goals, final result and news about the team.

Run by the ``football`` worker role. Each cycle reads the games football-data.org lists (one cached call shared
with the API, refreshed every minute while a game is on) and compares each game someone cares about with the
state saved last time in ``football_match_states``:

- scheduled -> in play: kickoff;
- a side's score went up: goal (with the score);
- anything -> finished: final result (with the team's place in the table when known).

A game seen for the first time is only recorded, so a deploy or a new favourite never replays old events.
News: a recent football article whose headline names a favourite team (at most TEAM_NEWS_PER_DAY a day per
team, never during quiet hours). A story is one delivery per team whichever outlet's article names the team, and is
skipped when a breaking-news push (or the alert of another favourite team) already told it. Every alert respects the
main switch, its own switch and the device permission, and reaches each person once (the job's delivery id is unique
per event).
"""
import json
import logging
import os
import re
import time
import unicodedata
import uuid
from datetime import timedelta

from .football import COMPETITIONS, FootballService, LIVE, UPCOMING, _kickoff, _team, football_service
from .notifications import NotificationService, wants
from .timeutil import iso, utc_now

log = logging.getLogger(__name__)
TEAM_NEWS_PER_DAY = int(os.getenv("TEAM_NEWS_PER_DAY", "3"))
NEWS_WINDOW = timedelta(hours=3)
# How fans name some clubs in headlines, besides the display name.
ALIASES = {"Atlético-MG": ["Atlético Mineiro", "Galo"], "Athletico-PR": ["Athletico"], "Red Bull Bragantino": ["Bragantino"],
           "Vasco": ["Vasco da Gama"], "Atlético-GO": ["Atlético Goianiense"], "São Paulo": ["Tricolor Paulista"]}
FOOTBALL_TOPICS = ("FUTEBOL", "BRASILEIRAO", "LIBERTADORES", "COPA_DO_BRASIL")


def _fold(value):
    return "".join(ch for ch in unicodedata.normalize("NFD", (value or "").lower()) if unicodedata.category(ch) != "Mn")


def _name_pattern(name):
    names = [name, *ALIASES.get(name, [])]
    return re.compile(r"(?<![\w-])(" + "|".join(re.escape(_fold(item)) for item in names) + r")(?![\w-])")


class FootballAlertService:
    def __init__(self, repo, service=None):
        self.repo = repo
        self.service = service or football_service()
        self.notifications = NotificationService(repo)
        self._last_games = self._last_news = None

    # Audience
    def _interest(self):
        """team id -> users who favourite it; match id -> users who follow that game."""
        teams, matches = {}, {}
        for row in self.repo.db.execute("SELECT f.user_id,f.team_id FROM user_favorite_teams f JOIN users u ON u.id=f.user_id WHERE u.status='ACTIVE'"):
            teams.setdefault(row["team_id"], set()).add(row["user_id"])
        for row in self.repo.db.execute("SELECT m.user_id,m.match_id FROM user_followed_matches m JOIN users u ON u.id=m.user_id WHERE u.status='ACTIVE'"):
            matches.setdefault(row["match_id"], set()).add(row["user_id"])
        return teams, matches

    def run_once(self, now=None, force=False):
        if not FootballService.configured():
            return {"status": "NOT_CONFIGURED"}
        teams, matches = self._interest()
        if not teams and not matches:
            return {"status": "NO_SUBSCRIBERS"}
        now = now or utc_now()
        result = {"status": "CHECKED", "game_alerts": 0, "news_alerts": 0}
        # Games every minute (the provider's list is cached for the same minute); news every five.
        if force or self._last_games is None or time.monotonic() - self._last_games >= 60:
            self._last_games = time.monotonic()
            try:
                result["game_alerts"] = self.check_games(teams, matches, now)
            except Exception as exc:
                log.warning("football game alerts failed: %s", exc)
        if force or self._last_news is None or time.monotonic() - self._last_news >= 300:
            self._last_news = time.monotonic()
            result["news_alerts"] = self.check_news(teams, now)
        return result

    # Games
    def check_games(self, teams, followed, now):
        sent = 0
        for match in self.service.raw_matches(now):
            home, away = match.get("homeTeam") or {}, match.get("awayTeam") or {}
            users = teams.get(home.get("id"), set()) | teams.get(away.get("id"), set()) | followed.get(match.get("id"), set())
            if not users or not match.get("id"):
                continue
            full = (match.get("score") or {}).get("fullTime") or {}
            status, home_goals, away_goals = match.get("status"), full.get("home"), full.get("away")
            previous = self.repo.db.execute("SELECT status,home_goals,away_goals FROM football_match_states WHERE match_id=?", (match["id"],)).fetchone()
            self.repo.db.execute("""INSERT INTO football_match_states(match_id,status,home_goals,away_goals,updated_at) VALUES(?,?,?,?,?)
                ON CONFLICT(match_id) DO UPDATE SET status=excluded.status,home_goals=excluded.home_goals,away_goals=excluded.away_goals,updated_at=excluded.updated_at""",
                (match["id"], status, home_goals, away_goals, iso(now)))
            self.repo.db.commit()
            if previous is None:
                continue  # first sight: just remember it
            for kind, payload, key in self._events(match, previous, status, home_goals, away_goals):
                for user_id in users:
                    sent += self._enqueue(user_id, kind, key, self._personal(kind, payload, match, user_id, teams), now)
        return sent

    def _events(self, match, previous, status, home_goals, away_goals):
        home, away = _team(match.get("homeTeam")), _team(match.get("awayTeam"))
        competition = COMPETITIONS.get((match.get("competition") or {}).get("code"), (match.get("competition") or {}).get("name") or "")
        where = f"{competition} · Rodada {match['matchday']}" if match.get("matchday") else competition
        score = f"{home} {home_goals or 0} x {away_goals or 0} {away}"
        data = {"match_id": str(match["id"]), "competition": (match.get("competition") or {}).get("code") or ""}
        events = []
        if previous["status"] in UPCOMING and status in LIVE:
            events.append(("TEAM_KICKOFF", {"title": f"Começou: {home} x {away}", "body": f"{where}. Acompanhe o placar no Newzi.", "data": data}, "kickoff"))
        if status in LIVE | {"FINISHED"}:
            before_home, before_away = previous["home_goals"] or 0, previous["away_goals"] or 0
            scorer = home if (home_goals or 0) > before_home else away if (away_goals or 0) > before_away else None
            if scorer:
                events.append(("TEAM_GOAL", {"title": f"Gol do {scorer}!", "body": f"{score} · {competition}", "data": data}, f"goal:{home_goals}-{away_goals}"))
        if previous["status"] != "FINISHED" and status == "FINISHED":
            winner = home if (home_goals or 0) > (away_goals or 0) else away if (away_goals or 0) > (home_goals or 0) else None
            events.append(("TEAM_FINAL", {"title": f"Fim de jogo: {score}", "body": f"{'Vitória do ' + winner if winner else 'Empate'} · {where}", "data": data}, "final"))
        return events

    def _personal(self, kind, payload, match, user_id, teams):
        """The final result adds the place in the table of this person's team, when the table is at hand."""
        if kind != "TEAM_FINAL":
            return payload
        code = (match.get("competition") or {}).get("code")
        mine = next((side for side in ("homeTeam", "awayTeam") if user_id in teams.get((match.get(side) or {}).get("id"), set())), None)
        if not mine or code not in COMPETITIONS:
            return payload
        try:
            rows = [row for group in self.service.standings(code)["groups"] for row in group["rows"]]
        except Exception:
            return payload
        row = next((row for row in rows if row.get("team_id") == (match.get(mine) or {}).get("id")), None)
        if not row:
            return payload
        return {**payload, "body": f"{payload['body']}. {row['team']} está em {row['position']}º com {row['points']} pontos."}

    def _enqueue(self, user_id, kind, key, payload, now, delivery_id=None):
        if not wants(self.notifications.settings(user_id), kind):
            return 0
        delivery_id = delivery_id or f"football:{payload['data'].get('match_id')}:{key}"
        message = {**payload, "data": {"type": kind, **payload["data"]}}
        created = 0
        for device in self.repo.db.execute("SELECT id FROM push_devices WHERE user_id=? AND enabled=1 AND invalidated_at IS NULL", (user_id,)).fetchall():
            cursor = self.repo.db.execute(
                """INSERT INTO notification_jobs(id,user_id,delivery_id,device_id,notification_type,scheduled_for,status,attempt_count,
                   max_attempts,next_attempt_at,provider_message_id,last_error,created_at,updated_at,payload_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING""",
                ("notification_" + uuid.uuid4().hex, user_id, delivery_id, device["id"], kind, iso(now), "PENDING", 0, 3, None, None, None,
                 iso(now), iso(now), json.dumps(message, ensure_ascii=False)))
            created += cursor.rowcount
        self.repo.db.commit()
        return created

    # News
    def check_news(self, teams, now):
        from .breaking import BreakingNewsService, already_told, story_summary
        quiet = BreakingNewsService(self.repo)
        if not teams:
            return 0
        names = {row["id"]: row["name"] for row in self.repo.db.execute(
            f"SELECT id,name FROM football_teams WHERE id IN ({','.join('?' for _ in teams)})", tuple(teams))}
        marks = ",".join("?" for _ in FOOTBALL_TOPICS)
        articles = self.repo.db.execute(
            f"""SELECT DISTINCT c.id,c.title,c.description,c.event_id,c.published_at FROM indexed_content c
                JOIN content_taxonomy t ON t.content_id=c.id
                WHERE c.published_at>=? AND c.published_at<=? AND (t.taxonomy_id IN ({marks}) OR t.taxonomy_id LIKE 'FUTEBOL%')
                ORDER BY c.published_at DESC""",
            (iso(now - NEWS_WINDOW), iso(now + timedelta(minutes=10)), *FOOTBALL_TOPICS)).fetchall()
        sent = 0; members = {}
        for team_id, name in names.items():
            pattern = _name_pattern(name)
            seen_events = set()
            for article in articles:
                if not pattern.search(_fold(article["title"])):
                    continue
                story = article["event_id"] or article["id"]
                if story in seen_events:
                    continue
                seen_events.add(story)
                if story not in members:
                    members[story] = {row[0] for row in self.repo.db.execute(
                        "SELECT id FROM indexed_content WHERE event_id=?", (article["event_id"],))} | {article["id"]} if article["event_id"] else {article["id"]}
                payload = {"title": article["title"], "body": story_summary(article["title"], [article["description"]]) or f"Notícia sobre o {name}. Toque para ler.",
                           "data": {"story_id": article["id"], "team_id": str(team_id)}}
                for user_id in teams[team_id]:
                    if (not quiet._awake(self.repo.get_preferences(user_id) or {}, now) or self._news_today(user_id, team_id, now) >= TEAM_NEWS_PER_DAY
                            or already_told(self.repo, user_id, members[story], article["title"], now)):
                        continue
                    # The delivery id names the story (event), not the article: a new outlet's article is not a new alert.
                    sent += self._enqueue(user_id, "TEAM_NEWS", None, payload, now, delivery_id=f"football:news:team:{team_id}:story:{story}")
        return sent

    def _news_today(self, user_id, team_id, now):
        return self.repo.db.execute(
            """SELECT COUNT(DISTINCT delivery_id) FROM notification_jobs WHERE user_id=? AND notification_type='TEAM_NEWS'
               AND delivery_id LIKE ? AND created_at>=? AND status<>'CANCELLED'""",
            (user_id, f"football:%:team:{team_id}:%", iso(now - timedelta(hours=24)))).fetchone()[0]
