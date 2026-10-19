"""Timestamps, worker roles and health, breaking-news push and the TTS fallback."""
import io
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

import servers
import support
from conftest import add_user
from contract_scenario import Client

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------- timestamps
def test_timestamps_have_one_sortable_format():
    from newzi_backend.timeutil import iso, normalize, parse
    assert iso(datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)) == "2026-01-02T03:04:05.000Z"
    assert iso(datetime(2026, 1, 2, 0, 4, 5, 7999, tzinfo=timezone(timedelta(hours=-3)))) == "2026-01-02T03:04:05.007Z"
    assert normalize("2026-01-02T03:04:05Z") == normalize("2026-01-02T03:04:05+00:00") == "2026-01-02T03:04:05.000Z"
    assert normalize("2026-01-02 03:04:05") == "2026-01-02T03:04:05.000Z"
    assert normalize("2026-01-02") == "2026-01-02" and normalize("t") == "t" and normalize(None) is None
    assert parse("2026-01-02T03:04:05Z") == parse("2026-01-02T00:04:05-03:00")
    # The old mix compared wrongly as text within the same second; the canonical form does not.
    assert "2026-01-02T03:04:05Z" > "2026-01-02T03:04:05.900000+00:00"
    assert normalize("2026-01-02T03:04:05Z") < normalize("2026-01-02T03:04:05.900000+00:00")


# ---------------------------------------------------------------- worker roles and health
def test_worker_roles_parse_and_validate():
    from newzi_backend.scheduling import WORKER_ROLES, parse_worker_roles
    assert parse_worker_roles("all") == parse_worker_roles("") == frozenset(WORKER_ROLES)
    assert parse_worker_roles("news:audio") == parse_worker_roles("audio, news") == {"news", "audio"}
    with pytest.raises(ValueError):
        parse_worker_roles("audio,emails")


def test_worker_runs_only_its_roles_and_reports_health(repo, monkeypatch):
    from newzi_backend import scheduling
    support.install_fake_tts()
    calls = []
    for owner, method, role in ((scheduling.BriefingScheduler, "run_once", "schedule"),
                                (scheduling.BriefingGenerationWorker, "run_batch", "generation")):
        monkeypatch.setattr(owner, method, lambda self, *a, _role=role, **k: calls.append(_role) or {})
    audio_worker = scheduling.BriefingDeliveryWorker(repo, roles="audio")
    result = audio_worker.cycle()
    assert calls == [] and set(result) == {"roles", "audio_jobs_enqueued", "audio"}

    health = scheduling.worker_health(repo)
    assert health["status"] == "degraded" and health["roles"]["audio"] <= 5
    assert "notifications" in health["missing_roles"] and "audio" not in health["missing_roles"]
    assert set(health["queues"]) == {"generation", "audio", "notifications", "manual_refresh"}
    assert "worker_id" not in json.dumps(health) and "last_error" not in json.dumps(health)

    monkeypatch.setattr(scheduling.NewsRefreshWorker, "refresh_if_due", lambda self, force=False: {"status": "READY"})
    rest = scheduling.BriefingDeliveryWorker(repo, roles=set(scheduling.WORKER_ROLES) - {"audio"})
    rest.cycle()
    assert scheduling.worker_health(repo)["status"] == "ok"
    assert scheduling.worker_health(repo, now=datetime.now(timezone.utc) + timedelta(hours=1))["status"] == "degraded"


def test_failed_cycle_is_recorded_not_raised(repo, monkeypatch):
    from newzi_backend import scheduling
    support.install_fake_tts()
    worker = scheduling.BriefingDeliveryWorker(repo, roles="schedule")
    monkeypatch.setattr(scheduling.BriefingScheduler, "run_once", lambda self: 1 / 0)
    assert worker.cycle() is None
    row = repo.db.execute("SELECT last_error,last_success_at,cycles FROM worker_heartbeats").fetchone()
    assert row["last_error"].startswith("ZeroDivisionError") and row["last_success_at"] is None and row["cycles"] == 1
    assert scheduling.worker_health(repo)["workers"][0]["last_cycle_failed"] is True


def test_stale_ingestion_run_no_longer_blocks_refresh(repo, monkeypatch):
    from newzi_backend import scheduling
    from newzi_backend.timeutil import iso
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(scheduling, "_engine_collect_sources", lambda: (lambda incremental=True: ({}, [])))
    insert = "INSERT INTO content_ingestion_runs(id,status,started_at) VALUES(?,'RUNNING',?)"
    repo.db.execute(insert, ("fresh", iso(now - timedelta(minutes=5)))); repo.db.commit()
    worker = scheduling.NewsRefreshWorker(repo, timeout_minutes=30)
    assert worker.refresh_if_due()["skipped"] == "IN_PROGRESS"             # a live run is still respected

    repo.db.execute("DELETE FROM content_ingestion_runs")
    repo.db.execute(insert, ("crashed", iso(now - timedelta(days=7)))); repo.db.commit()
    result = worker.refresh_if_due()
    assert result["id"] != "crashed" and result["status"] == "READY"
    crashed = repo.db.execute("SELECT status,completed_at,errors_json FROM content_ingestion_runs WHERE id='crashed'").fetchone()
    assert crashed["status"] == "FAILED" and crashed["completed_at"] and "WORKER_TIMEOUT" in crashed["errors_json"]


def test_worker_health_endpoint_is_503_without_workers():
    with servers.running(os.getenv("TEST_DATABASE_URL")) as (base_url, _seed):
        status, body, _ = Client(base_url).request("GET", "/health/worker")
    assert status == 503 and body["status"] == "degraded" and body["workers"] == []


# ---------------------------------------------------------------- breaking news
def add_article(repo, article_id, event_id, source, minutes_ago, title="Terremoto atinge capital e deixa feridos",
                topic="TECHNOLOGY", country="BR", description="Tremor de magnitude 6,1 derrubou prédios no centro e a Defesa Civil confirmou 40 feridos."):
    from newzi_backend.timeutil import iso
    published = iso(NOW - timedelta(minutes=minutes_ago))
    repo.db.execute("""INSERT INTO indexed_content(id,content_hash,title,description,url,source_name,source_id,source_country,source_language,
        published_at,indexed_at,enrichment_mode,quality_score,event_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (article_id, "h_" + article_id, title, description, "https://news.example/" + article_id, source.title(), source,
                     country, "pt-BR", published, published, "test", 5.0, event_id))
    repo.db.execute("INSERT INTO content_taxonomy(content_id,taxonomy_id,score) VALUES(?,?,?)", (article_id, topic, 8.0))
    repo.db.commit()


def add_event(repo, event_id, sources=5, start_minutes_ago=60, **kwargs):
    for index in range(sources):
        add_article(repo, f"{event_id}_{index}", event_id, f"source_{index}", start_minutes_ago - index * 10, **kwargs)


def subscribe(repo, uid, breaking=True, **prefs):
    from newzi_backend.notifications import NotificationService
    add_user(repo, uid, **prefs)
    service = NotificationService(repo)
    service.save_settings(uid, {"breaking_news_enabled": breaking})
    service.register_device(uid, {"platform": "ANDROID", "push_token": f"token-{uid}-123456"})


def breaking_jobs(repo, uid=None):
    sql = "SELECT * FROM notification_jobs WHERE notification_type='BREAKING_NEWS'" + (" AND user_id=?" if uid else "")
    return repo.db.execute(sql, (uid,) if uid else ()).fetchall()


def test_breaking_news_reaches_matching_opted_in_users_once(repo):
    from newzi_backend.breaking import BreakingNewsService
    subscribe(repo, "fan")
    subscribe(repo, "opted_out", breaking=False)
    subscribe(repo, "other_topic", topics=("SPORTS",))
    subscribe(repo, "night_owl", timezone="Asia/Tokyo")          # 12:00 UTC is 21:00 there, before quiet hours
    add_event(repo, "quake")
    service = BreakingNewsService(repo)
    result = service.run_once(NOW, force=True)
    assert result["events"] == 1
    assert {row["user_id"] for row in breaking_jobs(repo)} == {"fan", "night_owl"}
    payload = json.loads(breaking_jobs(repo, "fan")[0]["payload_json"])
    assert payload["title"].startswith("Terremoto") and payload["body"].startswith("Tremor de magnitude 6,1")
    assert "veículos" not in payload["body"]
    assert payload["data"] == {"type": "BREAKING_NEWS", "event_id": "quake", "story_id": payload["data"]["story_id"],
                               "url": payload["data"]["url"]}
    service.run_once(NOW + timedelta(minutes=5), force=True)
    assert len(breaking_jobs(repo)) == 2


def test_breaking_summary_is_a_short_clean_story_summary():
    from newzi_backend.breaking import story_summary
    title = "Terremoto atinge capital"
    assert story_summary(title, ["Terremoto atinge capital", "<p>Terremoto atinge capital. Tremor de 6,1 derrubou pr&eacute;dios no centro.</p> Leia mais"])         == "Tremor de 6,1 derrubou prédios no centro."
    long = "Primeira frase do texto explica o que aconteceu na cidade durante a manhã de hoje com muitos detalhes. " * 3
    summary = story_summary(title, [long])
    assert len(summary) <= 160 and summary.endswith(".")
    assert story_summary(title, ["Curto.", None, ""]) is None


def test_breaking_push_without_a_description_invites_to_read_and_skips_a_story_already_told(repo, monkeypatch):
    from newzi_backend.breaking import BreakingNewsService
    monkeypatch.setenv("BREAKING_MIN_GAP_MINUTES", "0")        # only the "already told" rule may hold the second push back
    subscribe(repo, "fan")
    add_event(repo, "quake", description="")
    service = BreakingNewsService(repo)
    service.run_once(NOW, force=True)
    assert json.loads(breaking_jobs(repo, "fan")[0]["payload_json"])["body"] == "Toque para ler a matéria completa no Newzi."
    # Re-clustering gives the same story a new event id: it is not sent again.
    for row in repo.db.execute("SELECT id FROM indexed_content WHERE event_id='quake'").fetchall():
        repo.db.execute("UPDATE indexed_content SET event_id='quake_v2' WHERE id=?", (row["id"],))
    repo.db.commit()
    service.run_once(NOW + timedelta(minutes=10), force=True)
    assert {row["delivery_id"] for row in breaking_jobs(repo)} == {"breaking_quake"}


def test_breaking_news_rules_skip_weak_old_and_promotional_events(repo):
    from newzi_backend.breaking import BreakingNewsService
    subscribe(repo, "fan")
    add_event(repo, "two_sources", sources=2)
    add_event(repo, "slow_story", sources=3, start_minutes_ago=120, title="Prefeitura anuncia novo plano de obras")   # 3 outlets over 2 h
    add_event(repo, "old_story", start_minutes_ago=600)
    add_article(repo, "old_story_late_1", "old_story", "late_1", 30)
    add_article(repo, "old_story_late_2", "old_story", "late_2", 20)
    add_event(repo, "deal", title="As melhores ofertas de celular do dia")
    assert BreakingNewsService(repo).detect(NOW) == []


def test_breaking_news_respects_quiet_hours(repo, monkeypatch):
    from newzi_backend.breaking import BreakingNewsService, in_quiet_hours
    assert in_quiet_hours(23, (22, 7)) and in_quiet_hours(3, (22, 7)) and not in_quiet_hours(12, (22, 7))
    subscribe(repo, "sleeper", timezone="America/Sao_Paulo")
    monkeypatch.setenv("BREAKING_QUIET_HOURS", "8-10")           # 12:00 UTC is 09:00 in Sao Paulo
    add_event(repo, "first")
    BreakingNewsService(repo).run_once(NOW, force=True)
    assert breaking_jobs(repo) == []
    monkeypatch.setenv("BREAKING_QUIET_HOURS", "")
    BreakingNewsService(repo).run_once(NOW, force=True)
    assert {row["delivery_id"] for row in breaking_jobs(repo)} == {"breaking_first"}


def test_breaking_news_waits_for_the_gap_then_sends_the_strongest_story_still_breaking(repo):
    from newzi_backend.breaking import BreakingNewsService
    subscribe(repo, "fan")
    service = BreakingNewsService(repo)
    add_event(repo, "first")
    service.run_once(NOW, force=True)
    add_event(repo, "weaker", sources=5, start_minutes_ago=30, title="Enchente isola cidades do litoral")
    add_event(repo, "stronger", sources=7, start_minutes_ago=30, title="Apagão atinge três estados do Nordeste")
    service.run_once(NOW + timedelta(minutes=5), force=True)
    assert {row["delivery_id"] for row in breaking_jobs(repo)} == {"breaking_first"}              # inside the 45 min gap
    service.run_once(NOW + timedelta(minutes=46), force=True)
    assert {row["delivery_id"] for row in breaking_jobs(repo)} == {"breaking_first", "breaking_stronger"}
    service.run_once(NOW + timedelta(minutes=92), force=True)                                       # the weaker one went quiet meanwhile
    assert {row["delivery_id"] for row in breaking_jobs(repo)} == {"breaking_first", "breaking_stronger"}


def test_breaking_news_daily_limit_lets_only_an_exceptional_story_through(repo, monkeypatch):
    from newzi_backend.breaking import BreakingNewsService
    monkeypatch.setenv("BREAKING_MIN_GAP_MINUTES", "0")
    monkeypatch.setenv("BREAKING_DAILY_LIMIT", "2")
    subscribe(repo, "fan", timezone="America/Sao_Paulo")
    service = BreakingNewsService(repo)
    add_event(repo, "a", title="Terremoto atinge capital e deixa feridos")
    add_event(repo, "b", title="Enchente isola cidades do litoral")
    add_event(repo, "c", title="Incêndio fecha rodovia no interior")
    service.run_once(NOW, force=True)
    assert len({row["delivery_id"] for row in breaking_jobs(repo)}) == 2
    add_event(repo, "huge", sources=10, start_minutes_ago=70, title="Apagão atinge três estados do Nordeste")
    service.run_once(NOW + timedelta(minutes=10), force=True)
    assert "breaking_huge" in {row["delivery_id"] for row in breaking_jobs(repo)}
    # The next local day starts a new count.
    add_event(repo, "tomorrow", start_minutes_ago=-24 * 60 + 60, title="Ponte desaba após forte chuva no Sul")
    service.run_once(NOW + timedelta(hours=24), force=True)
    assert len({row["delivery_id"] for row in breaking_jobs(repo)}) == 4


def test_breaking_news_needs_five_outlets_and_only_reaches_followers_of_the_topic(repo):
    from newzi_backend.breaking import BreakingNewsService
    subscribe(repo, "football_fan", topics=("SPORTS",))
    subscribe(repo, "tech_fan", topics=("TECHNOLOGY",))
    add_event(repo, "derby", sources=5, topic="SPORTS", title="Flamengo vence clássico e assume a liderança")
    add_event(repo, "rumor", sources=4, topic="SPORTS", title="Técnico pode deixar o clube no fim do ano")
    BreakingNewsService(repo).run_once(NOW, force=True)
    assert [(row["user_id"], row["delivery_id"]) for row in breaking_jobs(repo)] == [("football_fan", "breaking_derby")]


def test_breaking_push_is_sent_with_its_payload_or_dropped_when_stale(repo):
    from newzi_backend.breaking import BreakingNewsService
    from newzi_backend.notifications import NotificationService, PushResult
    subscribe(repo, "fan")
    add_event(repo, "quake")
    BreakingNewsService(repo).run_once(NOW, force=True)
    sent = []

    class Recording:
        name = "recording"
        def send(self, token, title, body, data): sent.append((title, body, data)); return PushResult(True, "m")
    notifications = NotificationService(repo, provider=Recording())
    assert notifications.run_once(NOW + timedelta(minutes=1))["notifications_sent"] == 1
    assert sent[0][0].startswith("Terremoto") and sent[0][2]["type"] == "BREAKING_NEWS"

    add_event(repo, "aftershock", start_minutes_ago=-300)
    repo.db.execute("DELETE FROM notification_jobs"); repo.db.commit()
    BreakingNewsService(repo).run_once(NOW + timedelta(hours=6), force=True)
    assert notifications.run_once(NOW + timedelta(hours=8))["cancelled"] == 1 and len(sent) == 1


# ---------------------------------------------------------------- TTS fallback
class Flaky:
    name, version, extension = "edge-tts", "x", ".mp3"
    def __init__(self, error=None): self.error = error; self.calls = 0
    def list_voices(self): return ["voice"]
    def health_check(self): return True
    def capabilities(self): return {}
    def synthesize(self, text, voice, language, options=None):
        self.calls += 1
        if self.error: raise self.error
        return {"path": "p", "resolved_voice": voice}
    synthesize_segments = synthesize


def test_tts_fallback_takes_over_and_cools_down(monkeypatch):
    from newzi_backend.audio import FallbackTTSProvider, PermanentAudioError
    monkeypatch.setattr(FallbackTTSProvider, "_primary_down_until", {})
    primary, standby = Flaky(ConnectionError("edge down")), Flaky()
    standby.name = "azure-tts"
    provider = FallbackTTSProvider(primary, standby, cooldown_seconds=600)
    assert (provider.name, provider.version) == ("edge-tts", "x")
    first = provider.synthesize("texto", "voice", "pt-BR")
    assert first["provider"] == "azure-tts" and first["fallback_reason"] == "ConnectionError"
    assert provider.synthesize_segments([{"text": "a"}], "voice", "pt-BR")["fallback_reason"] == "PRIMARY_COOLING_DOWN"
    assert primary.calls == 1 and standby.calls == 2

    monkeypatch.setattr(FallbackTTSProvider, "_primary_down_until", {})
    broken = FallbackTTSProvider(Flaky(PermanentAudioError("EMPTY_SCRIPT", "empty")), Flaky())
    with pytest.raises(PermanentAudioError):
        broken.synthesize("", "voice", "pt-BR")
    healthy = FallbackTTSProvider(Flaky(), standby)
    assert healthy.synthesize("texto", "voice", "pt-BR")["provider"] == "edge-tts"


def test_tts_provider_selection(monkeypatch):
    from newzi_backend.audio import AzureSpeechProvider, EdgeTTSProvider, FallbackTTSProvider, build_tts_provider
    monkeypatch.delenv("TTS_FALLBACK_PROVIDER", raising=False)
    monkeypatch.delenv("AZURE_SPEECH_KEY", raising=False)
    assert type(build_tts_provider("edge-tts")) is EdgeTTSProvider
    monkeypatch.setenv("AZURE_SPEECH_KEY", "k"); monkeypatch.setenv("AZURE_SPEECH_REGION", "brazilsouth")
    chained = build_tts_provider("edge-tts")
    assert isinstance(chained, FallbackTTSProvider) and isinstance(chained.fallback, AzureSpeechProvider)
    assert type(build_tts_provider("edge-tts", fallback_name="windows-sapi")) is EdgeTTSProvider   # different voices
    assert type(build_tts_provider("edge-tts", fallback_name="none")) is EdgeTTSProvider
    assert type(build_tts_provider("azure-tts")) is AzureSpeechProvider


def test_edge_passage_without_audio_is_read_with_a_standby_voice(monkeypatch, tmp_path):
    from edge_tts.exceptions import NoAudioReceived
    from newzi_backend import audio
    monkeypatch.setattr(audio.time, "sleep", lambda seconds: None)
    calls = []
    def render(self, text, voice, language, output):
        calls.append(voice)
        if voice == "pt-BR-ThalitaMultilingualNeural": raise NoAudioReceived("No audio was received.")
    monkeypatch.setattr(audio.EdgeTTSProvider, "_render", render)
    audio.EdgeTTSProvider()._render_with_standby("Trecho", "pt-BR-ThalitaMultilingualNeural", "pt-BR", tmp_path / "a.mp3")
    assert calls == ["pt-BR-ThalitaMultilingualNeural", "pt-BR-ThalitaMultilingualNeural", "pt-BR-FranciscaNeural"]
    assert audio.EdgeTTSProvider._standby_voice("en-US-AndrewMultilingualNeural", "pt-BR") == "pt-BR-AntonioNeural"


def test_azure_speech_request_and_errors(monkeypatch, tmp_path):
    import urllib.error
    import urllib.request
    from newzi_backend.audio import AzureSpeechProvider, PermanentAudioError
    captured = {}

    class Response(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *exc): return False

    def fake_urlopen(request, timeout):
        captured.update(url=request.full_url, headers=dict(request.header_items()), body=request.data.decode())
        return Response(b"ID3audio")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = AzureSpeechProvider(key="secret", region="brazilsouth")
    output = tmp_path / "out.mp3"
    provider._render("Juros & inflação <hoje>", "pt-BR-FranciscaNeural", "pt-BR", output)
    assert output.read_bytes() == b"ID3audio"
    assert captured["url"] == "https://brazilsouth.tts.speech.microsoft.com/cognitiveservices/v1"
    assert captured["headers"]["Ocp-apim-subscription-key"] == "secret"
    assert "<voice name=\"pt-BR-FranciscaNeural\">" in captured["body"] and "Juros &amp; inflação &lt;hoje&gt;" in captured["body"]

    def unauthorized(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", unauthorized)
    with pytest.raises(PermanentAudioError) as error:
        provider._render("x", "pt-BR-FranciscaNeural", "pt-BR", output)
    assert error.value.code == "TTS_NOT_CONFIGURED"
    with pytest.raises(PermanentAudioError):
        AzureSpeechProvider(key=None, region=None, endpoint=None)._render("x", "v", "pt-BR", output)
