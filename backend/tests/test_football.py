"""Esportes: favourite teams, team alerts (kickoff, goals, final, news) and cached crests."""
import io
import json
from datetime import datetime, timedelta, timezone

import pytest

NOW = datetime(2026, 10, 18, 22, 0, tzinfo=timezone.utc)
FLA = {"id": 1783, "shortName": "Flamengo", "tla": "FLA", "crest": "https://crests.football-data.org/1783.png"}
PAL = {"id": 1769, "shortName": "Palmeiras", "tla": "PAL", "crest": "https://crests.football-data.org/1769.png"}


@pytest.fixture()
def repo(repo, monkeypatch):
    from conftest import add_user
    monkeypatch.setenv("FOOTBALL_DATA_TOKEN", "test")
    add_user(repo, "fan"); add_user(repo, "other")
    from newzi_backend.football import remember_teams
    remember_teams(repo, [(FLA, "BSA"), (PAL, "BSA")])
    from newzi_backend.notifications import NotificationService
    for uid in ("fan", "other"):
        NotificationService(repo).register_device(uid, {"platform": "ANDROID", "push_token": f"token-{uid}-1234567"})
    return repo


class FakeFootball:
    def __init__(self): self.matches = []
    def raw_matches(self, now=None): return self.matches
    def standings(self, code):
        return {"groups": [{"rows": [{"team_id": 1783, "team": "Flamengo", "position": 1, "points": 72}]}]}


def game(status, home=0, away=0):
    return {"id": 900, "utcDate": "2026-10-18T21:30:00Z", "status": status, "matchday": 31, "competition": {"code": "BSA"},
            "homeTeam": FLA, "awayTeam": PAL, "score": {"fullTime": {"home": home if status != "TIMED" else None, "away": away if status != "TIMED" else None}}}


def jobs(repo, uid="fan"):
    return [(row["notification_type"], json.loads(row["payload_json"])) for row in
            repo.db.execute("SELECT notification_type,payload_json FROM notification_jobs WHERE user_id=? ORDER BY created_at,id", (uid,))]


def test_favourites_respect_the_plan_and_save_alert_switches(repo):
    from newzi_backend.football_favorites import FavoritesError, favorites, save_favorites
    saved = save_favorites(repo, "fan", {"team_ids": [1783], "alerts": {"goals": False}})
    assert [team["name"] for team in saved["teams"]] == ["Flamengo"] and saved["teams"][0]["crest"] == "/api/v1/football/crests/1783.png?v=2"
    assert saved["limit"] == 1 and saved["alerts"] == {"kickoff": True, "goals": False, "final": True, "news": True}
    with pytest.raises(FavoritesError) as limit:
        save_favorites(repo, "fan", {"team_ids": [1783, 1769]})
    assert limit.value.code == "FAVORITES_LIMIT"
    with pytest.raises(FavoritesError):
        save_favorites(repo, "fan", {"team_ids": [42]})
    assert [team["id"] for team in favorites(repo, "fan")["teams"]] == [1783]


def test_game_alerts_follow_the_score_once_and_never_replay_old_events(repo):
    from newzi_backend.football_alerts import FootballAlertService
    from newzi_backend.football_favorites import follow_match, save_favorites
    save_favorites(repo, "fan", {"team_ids": [1783]})
    follow_match(repo, "other", 900, True)
    football = FakeFootball(); service = FootballAlertService(repo, service=football)
    football.matches = [game("TIMED")]
    service.run_once(NOW, force=True)                                   # first sight: only remembered
    assert jobs(repo) == []
    football.matches = [game("IN_PLAY", 0, 0)]; service.run_once(NOW + timedelta(minutes=1), force=True)
    football.matches = [game("IN_PLAY", 1, 0)]; service.run_once(NOW + timedelta(minutes=2), force=True)
    service.run_once(NOW + timedelta(minutes=3), force=True)            # same score: nothing new
    football.matches = [game("FINISHED", 1, 0)]; service.run_once(NOW + timedelta(minutes=4), force=True)
    sent = jobs(repo)
    assert [kind for kind, _ in sent] == ["TEAM_KICKOFF", "TEAM_GOAL", "TEAM_FINAL"]
    assert sent[0][1]["title"] == "Começou: Flamengo x Palmeiras" and sent[0][1]["data"] == {"type": "TEAM_KICKOFF", "match_id": "900", "competition": "BSA"}
    assert sent[1][1]["title"] == "Gol do Flamengo!" and sent[1][1]["body"].startswith("Flamengo 1 x 0 Palmeiras")
    assert sent[2][1]["body"] == "Vitória do Flamengo · Brasileirão · Rodada 31. Flamengo está em 1º com 72 pontos."
    # The follower of the game (no favourite team) gets the same events, without the table line.
    assert [kind for kind, _ in jobs(repo, "other")] == ["TEAM_KICKOFF", "TEAM_GOAL", "TEAM_FINAL"]
    assert jobs(repo, "other")[2][1]["body"] == "Vitória do Flamengo · Brasileirão · Rodada 31"


def test_switched_off_alerts_are_not_queued(repo):
    from newzi_backend.football_alerts import FootballAlertService
    from newzi_backend.football_favorites import save_favorites
    save_favorites(repo, "fan", {"team_ids": [1783], "alerts": {"kickoff": False}})
    football = FakeFootball(); service = FootballAlertService(repo, service=football)
    football.matches = [game("TIMED")]; service.run_once(NOW, force=True)
    football.matches = [game("IN_PLAY", 0, 0)]; service.run_once(NOW, force=True)
    assert jobs(repo) == []


def test_team_news_reaches_fans_once_and_skips_other_teams(repo):
    from newzi_backend.football_alerts import FootballAlertService
    from newzi_backend.football_favorites import save_favorites
    from newzi_backend.timeutil import iso
    save_favorites(repo, "fan", {"team_ids": [1783]})
    noon = NOW.replace(hour=15)                                         # outside quiet hours in UTC
    for article_id, title, topic in (("a1", "Flamengo anuncia novo técnico para 2027", "FUTEBOL"),
                                     ("a2", "Flamenguistas lotam aeroporto", "FUTEBOL"),          # not the team's name
                                     ("a3", "Flamengo de Guarulhos inaugura praça", "TECHNOLOGY")):  # not football
        repo.db.execute("""INSERT INTO indexed_content(id,content_hash,title,description,url,source_name,source_id,source_country,source_language,
            published_at,indexed_at,enrichment_mode,quality_score,event_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (article_id, "h" + article_id, title, "O clube confirmou a contratação nesta tarde, depois de semanas de negociação.",
                         "https://x/" + article_id, "Ge", "ge", "BR", "pt-BR", iso(noon - timedelta(minutes=30)), iso(noon), "test", 5.0, None))
        repo.db.execute("INSERT INTO content_taxonomy(content_id,taxonomy_id,score) VALUES(?,?,?)", (article_id, topic, 8.0))
    repo.db.commit()
    service = FootballAlertService(repo, service=FakeFootball())
    service.run_once(noon, force=True); service.run_once(noon, force=True)
    sent = jobs(repo)
    assert [(kind, payload["data"]["story_id"]) for kind, payload in sent] == [("TEAM_NEWS", "a1")]
    assert sent[0][1]["body"].startswith("O clube confirmou")
    assert jobs(repo, "other") == []


def test_crest_is_downloaded_once_resized_and_served_from_disk(repo, tmp_path, monkeypatch):
    from PIL import Image
    from newzi_backend.football_favorites import crest_file
    monkeypatch.setenv("FOOTBALL_CREST_ROOT", str(tmp_path))
    buffer = io.BytesIO(); Image.new("RGBA", (300, 200), (200, 0, 0, 255)).save(buffer, "PNG")
    calls = []
    download = lambda url: calls.append(url) or buffer.getvalue()
    path = crest_file(repo, 1783, download=download)
    with Image.open(path) as crest:
        assert crest.size == (128, 128) and crest.getchannel("A").getbbox()[0::2] == (0, 128)   # fills the width
    small = io.BytesIO(); Image.new("RGBA", (70, 70), (0, 0, 0, 0)).save(small, "PNG")
    padded = Image.open(small).convert("RGBA"); padded.paste((0, 90, 0, 255), (10, 0, 60, 70)); small = io.BytesIO(); padded.save(small, "PNG")
    tiny = crest_file(repo, 1769, download=lambda url: small.getvalue())
    with Image.open(tiny) as crest:                                       # a 70 px crest is enlarged to the same height
        assert crest.getchannel("A").getbbox()[1] == 0 and crest.getchannel("A").getbbox()[3] == 128
    assert crest_file(repo, 1783, download=download) == path and len(calls) == 1
    assert crest_file(repo, 42, download=download) is None


def test_recent_form_and_rounds_come_from_the_season_games():
    from newzi_backend import football
    season = [
        {"id": 1, "utcDate": "2026-10-01T20:00:00Z", "status": "FINISHED", "matchday": 29, "homeTeam": FLA, "awayTeam": PAL, "competition": {"code": "BSA"}, "score": {"fullTime": {"home": 2, "away": 0}}},
        {"id": 2, "utcDate": "2026-10-08T20:00:00Z", "status": "FINISHED", "matchday": 30, "homeTeam": PAL, "awayTeam": FLA, "competition": {"code": "BSA"}, "score": {"fullTime": {"home": 1, "away": 1}}},
        {"id": 4, "utcDate": "2026-09-01T20:00:00Z", "status": "POSTPONED", "matchday": 21, "homeTeam": PAL, "awayTeam": FLA, "competition": {"code": "BSA"}, "score": {"fullTime": {}}},
        {"id": 3, "utcDate": "2026-10-19T20:00:00Z", "status": "TIMED", "matchday": 31, "homeTeam": FLA, "awayTeam": PAL, "competition": {"code": "BSA"}, "score": {"fullTime": {}}}]
    assert football._recent_form(season) == {1783: ["W", "D"], 1769: ["L", "D"]}
    service = football.FootballService(fetch=lambda path, params=None: {"matches": season})
    games = service.round_games("BSA")
    assert games["matchday"] == 31 and games["matchdays"] == [21, 29, 30, 31] and [m["id"] for m in games["matches"]] == [3]
    assert games["matches"][0]["home_crest"] == "/api/v1/football/crests/1783.png?v=2"
    assert service.round_games("BSA", 29)["matches"][0]["home_goals"] == 2
