"""Premium features: extra and themed briefings, "Gerar agora", the extended narration, history and search limits."""
from datetime import datetime, timezone

import pytest

from conftest import add_user

NOON = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def enforced(monkeypatch):
    monkeypatch.setenv("PREMIUM_ENFORCED", "true")


def scheduler_at(repo, moment=NOON):
    from newzi_backend.scheduling import BriefingScheduler, FixedClock
    return BriefingScheduler(repo, clock=FixedClock(moment), lead_minutes=10)


def test_extra_briefings_are_scheduled_each_at_its_time_with_its_theme(repo):
    from newzi_backend.briefing_slots import save_extra_slots
    from newzi_backend.scheduling import BriefingGenerationWorker, FixtureBriefingGenerator
    add_user(repo, "reader", "UTC", "06:00")
    save_extra_slots(repo, "reader", [{"time": "12:05", "theme": "SPORTS"}, {"time": "20:00", "length": "extended"}])
    result = scheduler_at(repo).run_once()
    # 06:00 is past and 12:05 is within the lead time; 20:00 is not due yet.
    jobs = {row["slot"]: row for row in repo.db.execute("SELECT * FROM generation_jobs WHERE user_id='reader'")}
    assert result["jobs_created"] == 2 and set(jobs) == {1, 2} and jobs[2]["delivery_time"] == "12:05"
    assert jobs[1]["profile_key"] != jobs[2]["profile_key"]
    worker = BriefingGenerationWorker(repo, generator=FixtureBriefingGenerator())
    worker.run_once(); worker.run_once()
    deliveries = {row["slot"]: row for row in repo.db.execute("SELECT * FROM user_briefing_deliveries WHERE user_id='reader'")}
    assert set(deliveries) == {1, 2} and deliveries[2]["kind"] == "EXTRA" and deliveries[2]["theme"] == "SPORTS"
    assert deliveries[1]["edition_id"] != deliveries[2]["edition_id"]
    assert scheduler_at(repo).run_once()["jobs_created"] == 0


def test_basico_keeps_only_the_daily_briefing_once_limits_are_enforced(repo, enforced):
    from newzi_backend.briefing_slots import save_extra_slots
    from newzi_backend.subscriptions import PremiumRequired, grant_manual
    add_user(repo, "free", "UTC", "06:00"); add_user(repo, "paid", "UTC", "06:00")
    with pytest.raises(PremiumRequired):
        save_extra_slots(repo, "free", [{"time": "12:05"}])
    grant_manual(repo, "paid")
    with pytest.raises(PremiumRequired):  # three briefings a day at most
        save_extra_slots(repo, "paid", [{"time": "12:05"}, {"time": "13:00"}, {"time": "14:00"}])
    with pytest.raises(ValueError):
        save_extra_slots(repo, "paid", [{"time": "06:00"}])   # the daily briefing's time
    save_extra_slots(repo, "paid", [{"time": "12:05"}])
    scheduler_at(repo).run_once()
    assert sorted(row[0] for row in repo.db.execute("SELECT slot FROM generation_jobs WHERE user_id='paid'")) == [1, 2]
    # When the plan ends the extra briefing stays saved but is no longer made.
    from newzi_backend.subscriptions import revoke_manual
    revoke_manual(repo, "paid")
    repo.db.execute("DELETE FROM generation_jobs"); repo.db.commit()
    scheduler_at(repo).run_once()
    assert [row[0] for row in repo.db.execute("SELECT slot FROM generation_jobs WHERE user_id='paid'")] == [1]


def test_next_briefing_is_the_soonest_of_the_day(repo):
    from newzi_backend.briefing_slots import save_extra_slots
    from newzi_backend.product_backend import ProductService
    from newzi_backend.scheduling import FixedClock
    add_user(repo, "reader", "UTC", "06:00")
    save_extra_slots(repo, "reader", [{"time": "18:30"}, {"time": "13:00", "theme": "ECONOMY"}])
    service = ProductService(repo, clock=FixedClock(NOON))
    assert service.preferences("reader")["next_briefing"] == {"date": "2026-10-19", "time": "13:00", "day": "TODAY", "slot": 3}
    late = ProductService(repo, clock=FixedClock(datetime(2026, 10, 19, 21, 0, tzinfo=timezone.utc)))
    assert late.preferences("reader")["next_briefing"] == {"date": "2026-10-20", "time": "06:00", "day": "TOMORROW"}


def test_on_demand_briefing_is_premium_limited_and_becomes_its_own_delivery(repo, enforced, monkeypatch):
    import support
    from newzi_backend.product_backend import ApiError, ProductService
    from newzi_backend.subscriptions import PremiumRequired, grant_manual
    support.seed_content(repo)
    add_user(repo, "reader", "UTC", "06:00", topics=support.SEED_TOPICS)
    service = ProductService(repo)
    with pytest.raises(PremiumRequired):
        service.request_on_demand("reader")
    grant_manual(repo, "reader")
    first = service.request_on_demand("reader")
    assert first["status"] == "PENDING" and service.request_on_demand("reader")["coalesced"]
    row = repo.db.execute("SELECT slot,reason FROM manual_refresh_requests WHERE id=?", (first["generation_id"],)).fetchone()
    assert (row["slot"], row["reason"]) == (10, "ON_DEMAND")
    # Five a day.
    repo.db.execute("UPDATE manual_refresh_requests SET status='READY'"); repo.db.commit()
    for _ in range(4):
        service.request_on_demand("reader")
        repo.db.execute("UPDATE manual_refresh_requests SET status='READY'"); repo.db.commit()
    with pytest.raises(ApiError) as limited:
        service.request_on_demand("reader")
    assert limited.value.code == "ON_DEMAND_LIMIT"
    assert sorted(row[0] for row in repo.db.execute("SELECT slot FROM manual_refresh_requests")) == [10, 11, 12, 13, 14]


def test_history_of_basico_shows_seven_days_and_search_is_premium(repo, enforced):
    from newzi_backend.product_backend import ProductService
    from newzi_backend.scheduling import FixedClock
    from newzi_backend.subscriptions import PremiumRequired, grant_manual
    add_user(repo, "reader", "UTC", "06:00")
    for day in range(1, 11):
        repo.db.execute("INSERT INTO briefing_editions(id,profile_key,edition_date,language,status,generated_at,item_count,created_at) VALUES(?,?,?,?,?,?,?,?)",
                        (f"e{day}", f"p{day}", f"2026-10-{day:02d}", "pt-BR", "READY", f"2026-10-{day:02d}T06:00:00.000000+00:00", 1, "t"))
        repo.db.execute("INSERT INTO briefing_edition_items(id,edition_id,position,event_id,headline,summary,key_points_json,warnings_json,sources_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (f"i{day}", f"e{day}", 1, f"ev{day}", "Copom mantém a Selic" if day == 2 else f"Notícia {day}", "Resumo", "[]", "[]", "[]", "t"))
        repo.db.execute("INSERT INTO user_briefing_deliveries(id,user_id,edition_id,local_date,delivery_time,timezone,status,created_at) VALUES(?,?,?,?,?,?,?,?)",
                        (f"d{day}", "reader", f"e{day}", f"2026-10-{day:02d}", "06:00", "UTC", "READY", f"2026-10-{day:02d}T06:00:00.000000+00:00"))
    repo.db.commit()
    service = ProductService(repo, clock=FixedClock(datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)))
    page = service.history_page("reader", 20, 0)
    assert [item["date"] for item in page["items"]][-1] == "2026-10-04" and len(page["items"]) == 7
    assert page["limited"] == {"days": 7, "older_count": 3}
    with pytest.raises(PremiumRequired):
        service.search_briefings("reader", "selic")
    grant_manual(repo, "reader")
    assert len(service.history_page("reader", 20, 0)["items"]) == 10 and "limited" not in service.history_page("reader", 20, 0)
    found = service.search_briefings("reader", "copom SELIC")["items"]
    assert [(item["briefing_id"], item["item"]["headline"]) for item in found] == [("d2", "Copom mantém a Selic")]


def test_extended_narration_adds_what_other_outlets_reported():
    from newzi_backend.audio import AudioScriptComposer
    item = {"id": "i1", "headline": "Banco Central mantém juros", "summary": "O Banco Central manteve a taxa Selic em 15% ao ano nesta quarta-feira.",
            "why_it_matters": None, "warnings": [], "primary_taxonomy_id": "ECONOMY",
            "context": [("Valor", "O Banco Central manteve a taxa Selic em 15% ao ano."),
                        ("Folha", "Economistas esperam cortes a partir de março, quando a inflação deve recuar para perto da meta.")]}
    edition = {"status": "READY", "language": "pt-BR", "items": [item], "narration": "extended"}
    segments = AudioScriptComposer().compose(edition, "pt-BR")
    narrated = segments[1][2]
    assert "resumo estendido" in segments[0][2]
    assert "Segundo Folha, economistas esperam cortes" in narrated and "Segundo Valor" not in narrated  # Valor only repeated the lead
    standard = AudioScriptComposer().compose({**edition, "narration": "standard"}, "pt-BR")
    assert "Segundo" not in standard[1][2]


def test_slot_migration_keeps_existing_jobs_and_deliveries(tmp_path):
    from newzi_backend import db as database
    from newzi_backend.migrations import MIGRATIONS, migrate
    path = tmp_path / "old.sqlite3"
    connection = database.connect("sqlite:///" + path.as_posix(), sqlite_path=path)
    migrate(connection, MIGRATIONS[:10])
    connection.execute("""INSERT INTO generation_jobs(id,user_id,briefing_date,scheduled_for,delivery_time,timezone,status,created_at,profile_key)
        VALUES('j1','u1','2026-10-18','t','06:00','UTC','COMPLETED','t','p')""")
    connection.execute("""INSERT INTO user_briefing_deliveries(id,user_id,edition_id,local_date,delivery_time,timezone,status,created_at)
        VALUES('d1','u1','e1','2026-10-18','06:00','UTC','READY','t')""")
    connection.commit()
    assert migrate(connection) == ["0011_briefing_slots", "0012_premium_features", "0013_admin_panel", "0014_panel_writes"]
    row = connection.execute("SELECT id,slot,kind FROM user_briefing_deliveries").fetchone()
    assert (row["id"], row["slot"], row["kind"]) == ("d1", 1, "SCHEDULED")
    assert connection.execute("SELECT slot FROM generation_jobs WHERE id='j1'").fetchone()[0] == 1
    # A second briefing of the same day is now possible, a duplicate slot is not.
    connection.execute("""INSERT INTO user_briefing_deliveries(id,user_id,edition_id,local_date,delivery_time,timezone,status,created_at,slot)
        VALUES('d2','u1','e2','2026-10-18','18:00','UTC','READY','t',2)""")
    with pytest.raises(database.IntegrityError):
        connection.execute("""INSERT INTO user_briefing_deliveries(id,user_id,edition_id,local_date,delivery_time,timezone,status,created_at,slot)
            VALUES('d3','u1','e3','2026-10-18','18:00','UTC','READY','t',2)""")
    connection.rollback(); connection.close()


# ---------------------------------------------------------------- collections, alerts, football
def article(repo, article_id, title, published, event_id=None, description="", language="pt-BR"):
    from newzi_backend.timeutil import iso
    repo.db.execute("""INSERT INTO indexed_content(id,content_hash,title,description,url,source_name,source_id,source_language,published_at,
        indexed_at,enrichment_mode,first_seen_at,event_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (article_id, article_id, title, description, "https://x/" + article_id, "Outlet " + article_id, "src_" + article_id, language,
         iso(published), iso(published), "test", iso(published), event_id))
    repo.db.commit()


def device(repo, uid):
    from newzi_backend.notifications import NotificationService
    NotificationService(repo).register_device(uid, {"platform": "IOS", "push_token": f"fcm-{uid}-123456"})


def pushes(repo, uid, kind):
    import json
    return [json.loads(row[0]) for row in repo.db.execute("SELECT payload_json FROM notification_jobs WHERE user_id=? AND notification_type=? ORDER BY created_at,id", (uid, kind))]


def test_collections_keep_saved_stories_and_are_premium(repo, enforced):
    from newzi_backend.collections import collection_stories, create_collection, list_collections, set_membership
    from newzi_backend.product_backend import ApiError
    from newzi_backend.subscriptions import PremiumRequired, grant_manual
    add_user(repo, "reader")
    with pytest.raises(PremiumRequired):
        create_collection(repo, "reader", {"name": "Fim de semana"})
    grant_manual(repo, "reader")
    weekend = create_collection(repo, "reader", {"name": " Fim  de semana "})
    assert weekend["name"] == "Fim de semana" and weekend["count"] == 0
    with pytest.raises(ApiError):
        create_collection(repo, "reader", {"name": "fim de semana"})
    story = {"id": "s1", "headline": "Uma matéria longa", "image_url": "https://img/1.jpg"}
    assert set_membership(repo, "reader", weekend["id"], {"story": story})["collections"] == [weekend["id"]]
    assert [item["id"] for item in collection_stories(repo, "reader", weekend["id"])["items"]] == ["s1"]
    assert list_collections(repo, "reader")[0]["cover_image_url"] == "https://img/1.jpg"
    repo.remove_saved_story("reader", "s1")              # leaving Salvos leaves every collection
    assert list_collections(repo, "reader")[0]["count"] == 0


def test_keyword_alert_reaches_the_reader_once_and_respects_limits(repo):
    from datetime import timedelta
    from newzi_backend.alerts import PersonalAlertService, add_keyword
    add_user(repo, "reader"); device(repo, "reader")
    add_keyword(repo, "reader", {"keyword": "Petrobras"})
    service = PersonalAlertService(repo)
    service.run_once(NOON, force=True)                       # first run: nothing new yet
    article(repo, "a1", "Petrobrás anuncia nova descoberta no pré-sal", NOON + timedelta(minutes=2), "ev1", "A estatal confirmou o achado nesta segunda-feira em comunicado ao mercado.")
    article(repo, "a2", "Petrobras: ações sobem após descoberta", NOON + timedelta(minutes=3), "ev1")   # same story
    article(repo, "a3", "Vale divulga resultado", NOON + timedelta(minutes=3), "ev2")
    service.run_once(NOON + timedelta(minutes=5), force=True)
    sent = pushes(repo, "reader", "KEYWORD_ALERT")
    assert len(sent) == 1 and sent[0]["data"]["story_id"] in ("a1", "a2") and sent[0]["body"].startswith("“Petrobras” · ")
    service.run_once(NOON + timedelta(minutes=10), force=True)
    assert len(pushes(repo, "reader", "KEYWORD_ALERT")) == 1


def test_followed_story_pushes_its_updates_spaced_out(repo):
    from datetime import timedelta
    from newzi_backend.alerts import PersonalAlertService, follow_story
    from newzi_backend import alerts
    add_user(repo, "reader"); device(repo, "reader")
    article(repo, "s1", "Chuvas deixam cidades em alerta no Sul", NOON - timedelta(hours=1), "storm")
    import newzi_backend.alerts as module
    real_now = module.utc_now
    module.utc_now = lambda: NOON
    try:
        assert follow_story(repo, "reader", "s1")["following"]
    finally:
        module.utc_now = real_now
    service = PersonalAlertService(repo)
    article(repo, "s2", "Defesa Civil amplia alerta para mais 20 cidades", NOON + timedelta(minutes=20), "storm")
    service.run_once(NOON + timedelta(minutes=30), force=True)
    sent = pushes(repo, "reader", "STORY_UPDATE")
    assert len(sent) == 1 and sent[0]["title"] == "Novidade: Chuvas deixam cidades em alerta no Sul" and sent[0]["data"]["story_id"] == "s2"
    article(repo, "s3", "Rio transborda em Porto Alegre", NOON + timedelta(minutes=40), "storm")
    service.run_once(NOON + timedelta(minutes=50), force=True)          # within the 2 h gap
    assert len(pushes(repo, "reader", "STORY_UPDATE")) == 1
    service.run_once(NOON + timedelta(hours=3), force=True)
    assert [push["data"]["story_id"] for push in pushes(repo, "reader", "STORY_UPDATE")] == ["s2", "s3"]
    assert alerts.STORY_UPDATE_GAP == timedelta(hours=2)


def test_premium_fans_get_the_reminder_the_match_audio_and_the_live_activity(repo, monkeypatch):
    from datetime import timedelta
    from newzi_backend import live_activities, match_audio
    from newzi_backend.football import remember_teams
    from newzi_backend.football_alerts import FootballAlertService
    from newzi_backend.football_favorites import save_favorites
    monkeypatch.setenv("FOOTBALL_DATA_TOKEN", "test")
    add_user(repo, "fan"); device(repo, "fan")
    fla = {"id": 1783, "shortName": "Flamengo", "tla": "FLA", "crest": "https://crests/1783.png"}
    pal = {"id": 1769, "shortName": "Palmeiras", "tla": "PAL", "crest": "https://crests/1769.png"}
    remember_teams(repo, [(fla, "BSA"), (pal, "BSA")])
    save_favorites(repo, "fan", {"team_ids": [1783]})
    live_activities.register_token(repo, "fan", {"kind": "start", "token": "a" * 64, "push_token": "fcm-fan-123456"})
    sent = []
    monkeypatch.setattr(live_activities, "_fcm_sender", lambda repo: lambda fcm, token, aps: sent.append(aps) or True)

    class Football:
        matches = []
        def raw_matches(self, now=None): return self.matches
        def standings(self, code): return {"groups": [{"rows": [{"team_id": 1783, "team": "Flamengo", "position": 1, "points": 72},
                                                                 {"team_id": 1769, "team": "Palmeiras", "position": 2, "points": 70}]}]}
    def game(status, home=0, away=0):
        return {"id": 900, "utcDate": "2026-10-19T12:10:00Z", "status": status, "matchday": 31, "competition": {"code": "BSA"},
                "homeTeam": fla, "awayTeam": pal, "score": {"fullTime": {"home": home, "away": away}}}
    football = Football(); service = FootballAlertService(repo, service=football)
    football.matches = [game("TIMED", None, None)]
    service.run_once(NOON, force=True); service.run_once(NOON + timedelta(minutes=1), force=True)
    reminders = pushes(repo, "fan", "TEAM_REMINDER")
    assert len(reminders) == 1 and reminders[0]["title"] == "Começa em 10 min: Flamengo x Palmeiras"
    assert [aps["event"] for aps in sent] == ["start"] and sent[0]["attributes"]["homeTla"] == "FLA"
    live_activities.register_token(repo, "fan", {"kind": "update", "token": "b" * 64, "push_token": "fcm-fan-123456", "match_id": 900})
    football.matches = [game("IN_PLAY", 0, 0)]; service.run_once(NOON + timedelta(minutes=12), force=True)
    football.matches = [game("FINISHED", 2, 1)]
    monkeypatch.setattr(match_audio, "generate_pending", lambda repo, audio_service=None, limit=2: 0)
    service.run_once(NOON + timedelta(minutes=110), force=True)
    assert [aps["event"] for aps in sent] == ["start", "update", "end"] and sent[-1]["content-state"]["homeGoals"] == 2
    final = pushes(repo, "fan", "TEAM_FINAL")[0]
    assert final["data"]["match_audio"] == "1" and final["body"].endswith("Ouça o resumo do jogo no Newzi.")
    script = repo.db.execute("SELECT script,status FROM football_match_audio WHERE match_id=900").fetchone()
    assert script["status"] == "PENDING" and "Flamengo venceu Palmeiras por 2 a 1" in script["script"] and "1º lugar, com 72 pontos" in script["script"]


def test_match_audio_is_narrated_once_and_served_to_premium(repo, enforced):
    import support
    from newzi_backend import match_audio
    from newzi_backend.audio import AudioService
    from newzi_backend.subscriptions import PremiumRequired, grant_manual
    support.install_fake_tts()
    add_user(repo, "fan")
    match = {"id": 7, "status": "FINISHED", "homeTeam": {"shortName": "Santos"}, "awayTeam": {"shortName": "Grêmio"},
             "competition": {"code": "BSA"}, "matchday": 2, "score": {"fullTime": {"home": 1, "away": 1}}}
    assert match_audio.queue(repo, match) and not match_audio.queue(repo, match)
    assert match_audio.generate_pending(repo, AudioService(repo)) == 1
    with pytest.raises(PremiumRequired):
        match_audio.match_audio(repo, "fan", 7)
    grant_manual(repo, "fan")
    ready = match_audio.match_audio(repo, "fan", 7)
    assert ready["status"] == "READY" and ready["audio_url"].startswith("/api/v1/me/football/matches/7/audio/file")
    path, mime = match_audio.match_audio_file(repo, "fan", 7, AudioService(repo).storage.root)
    assert path.is_file() and mime == "audio/mpeg"


def test_saved_stories_become_one_narration_that_follows_the_list(repo):
    import support
    from newzi_backend.audio import AudioService
    from newzi_backend.saved_audio import saved_audio, saved_audio_file
    support.install_fake_tts()
    add_user(repo, "reader")
    audio = AudioService(repo)
    assert saved_audio(repo, audio, "reader")["status"] == "EMPTY"
    for index in range(3):
        repo.save_story("reader", {"id": f"s{index}", "headline": f"Matéria salva número {index}", "summary": f"Resumo da matéria salva número {index} com detalhes."})
    queued = saved_audio(repo, audio, "reader", create=True)
    assert queued["status"] == "PENDING" and queued["story_count"] == 3
    audio.generate_pending()
    ready = saved_audio(repo, audio, "reader")
    assert ready["status"] == "READY" and ready["audio_url"].startswith("/api/v1/me/saved/audio/file?edition=" + ready["edition_id"])
    assert saved_audio_file(repo, audio, "reader", ready["edition_id"])[0].is_file()
    script = [row[0] for row in repo.db.execute("SELECT text FROM audio_script_segments ORDER BY position")]
    assert script[0].startswith("Olá. Estas são as matérias que você salvou")
    repo.remove_saved_story("reader", "s0")
    assert saved_audio(repo, audio, "reader")["edition_id"] != ready["edition_id"]   # a new list is a new narration


def test_on_demand_audio_goes_first_and_the_briefing_is_delivered_as_soon_as_it_is_ready(repo):
    import support
    from newzi_backend.audio import AudioService
    from newzi_backend.product_backend import ProductService
    from newzi_backend.scheduling import BriefingGenerationWorker
    support.install_fake_tts(); support.seed_content(repo)
    add_user(repo, "reader", topics=support.SEED_TOPICS)
    audio = AudioService(repo)
    # An older audio and the day's scheduled briefing are already waiting.
    repo.db.execute("""INSERT INTO audio_generation_jobs(id,edition_id,language,voice,script_version,status,attempt_count,max_attempts,created_at,stage,updated_at)
        VALUES('older','other_edition','pt-BR','voice',?,'PENDING',0,3,'2000-01-01T00:00:00.000000+00:00','QUEUED','t')""", (audio.script_version,)); repo.db.commit()
    scheduler_at(repo).run_once()
    request = ProductService(repo).request_on_demand("reader")
    worker = BriefingGenerationWorker(repo, audio_service=audio)
    assert worker.manual_waiting()
    worker.run_batch()
    # The cycle goes on to the audio right away; the scheduled briefing waits for the next one.
    assert repo.db.execute("SELECT status FROM generation_jobs WHERE user_id='reader'").fetchone()[0] == "PENDING"
    assert repo.db.execute("SELECT stage FROM manual_refresh_requests WHERE id=?", (request["generation_id"],)).fetchone()[0] == "AUDIO_QUEUED"
    assert not worker.manual_waiting()
    assert audio.generate_pending()["jobs_completed"] == 1
    # Delivered by the audio job itself, with the older audio still in the queue.
    assert repo.db.execute("SELECT status FROM manual_refresh_requests WHERE id=?", (request["generation_id"],)).fetchone()[0] == "READY"
    delivery = repo.db.execute("SELECT status,kind FROM user_briefing_deliveries WHERE user_id='reader' AND slot=10").fetchone()
    assert (delivery["status"], delivery["kind"]) == ("READY", "ON_DEMAND")
    assert repo.db.execute("SELECT status FROM audio_generation_jobs WHERE id='older'").fetchone()[0] == "PENDING"


def test_on_demand_briefing_with_nothing_new_is_refused_at_once_and_shown_as_em_dia(repo):
    import support
    from newzi_backend.audio import AudioService
    from newzi_backend.product_backend import ApiError, ProductService
    from newzi_backend.scheduling import BriefingGenerationWorker
    support.install_fake_tts(); support.seed_content(repo)
    add_user(repo, "reader", topics=support.SEED_TOPICS)
    audio = AudioService(repo); service = ProductService(repo)
    worker = BriefingGenerationWorker(repo, audio_service=audio)
    news = service.on_demand_news("reader")
    assert news["new_count"] > 0 and not news["generating"]
    first = service.request_on_demand("reader")
    # A second tap while it is made follows the same briefing.
    assert service.request_on_demand("reader")["generation_id"] == first["generation_id"]
    assert service.on_demand_news("reader") == {"new_count": 0, "generating": True, "generation_id": first["generation_id"]}
    worker.run_batch(); audio.generate_pending()
    assert repo.db.execute("SELECT status FROM manual_refresh_requests WHERE id=?", (first["generation_id"],)).fetchone()[0] == "READY"
    # Everything was told: "Em dia", and a tap is answered at once, with no queue, audio or use of the day.
    assert service.on_demand_news("reader")["new_count"] == 0
    with pytest.raises(ApiError) as refused:
        service.request_on_demand("reader")
    assert (refused.value.code, refused.value.status) == ("NO_NEW_CONTENT", 409)
    assert repo.db.execute("SELECT COUNT(*) FROM manual_refresh_requests").fetchone()[0] == 1
    # The worker never repeats the earlier briefing either.
    from newzi_backend.timeutil import now_iso
    repo.db.execute("INSERT INTO manual_refresh_requests(id,user_id,reason,status,stage,requested_at,updated_at,slot) VALUES('again','reader','ON_DEMAND','PENDING','QUEUED',?,?,11)", (now_iso(), now_iso())); repo.db.commit()
    worker.run_batch()
    row = repo.db.execute("SELECT status,error_code FROM manual_refresh_requests WHERE id='again'").fetchone()
    assert (row["status"], row["error_code"]) == ("FAILED", "NO_ELIGIBLE_CONTENT")


def test_on_demand_news_is_kept_until_something_changes(repo, monkeypatch):
    import support
    from newzi_backend import content
    from newzi_backend.product_backend import ProductService
    support.seed_content(repo)
    add_user(repo, "reader", topics=support.SEED_TOPICS)
    service = ProductService(repo); calls = []
    compose = content.compose
    monkeypatch.setattr(content, "compose", lambda *args, **kwargs: calls.append(1) or compose(*args, **kwargs))
    first = service.on_demand_news("reader")["new_count"]
    assert service.on_demand_news("reader")["new_count"] == first and len(calls) == 1
    repo.db.execute("INSERT INTO content_ingestion_runs(id,status,started_at,completed_at) VALUES('run','COMPLETED','t','2026-10-25T21:00:00.000000+00:00')"); repo.db.commit()
    service.on_demand_news("reader")
    assert len(calls) == 2   # news were collected: counted again
