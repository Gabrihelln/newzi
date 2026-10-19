"""Portuguese readers get Portuguese coverage only, and Internacional is world news told in Portuguese too."""
from datetime import timedelta

from test_engine import NOW, index


def briefing(repo, language="pt-BR", scope="BOTH", topics=("WORLD",)):
    from newzi_backend.content import compose
    return compose(repo, list(topics), language, 5, scope, now=NOW, briefing_date=NOW.date().isoformat())["items"]


def test_a_story_only_in_english_is_left_out_for_a_portuguese_reader_and_told_in_portuguese_when_it_can(repo):
    index(repo, "nyt_vote", "nyt_world", "Parliament approves new budget", event_id="vote", topic="WORLD", language="en", quality=9.0)
    index(repo, "g1_vote", "g1_mundo", "Parlamento aprova novo orçamento", event_id="vote", topic="WORLD", country="BR", hours_ago=3)
    index(repo, "bbc_storm", "bbc_world", "Storm hits the coast", event_id="storm", topic="WORLD", language="en")
    items = briefing(repo)
    assert [(item["event_id"], item["headline"]) for item in items] == [("vote", "Parlamento aprova novo orçamento")]
    assert "SOURCE_LANGUAGE_FALLBACK" not in items[0]["warnings"]
    # An English reader keeps every story.
    assert {item["event_id"] for item in briefing(repo, language="en")} == {"vote", "storm"}


def test_internacional_includes_the_brazilian_world_desks_but_not_other_brazilian_outlets(repo):
    index(repo, "folha_war", "folha_mundo", "Cessar-fogo começa na fronteira", event_id="war", topic="WORLD", country="BR")
    index(repo, "dw_war", "dw_brasil", "Trégua entra em vigor", event_id="truce", topic="WORLD", country="DE", hours_ago=2)
    index(repo, "uol_city", "uol", "Prefeitura anuncia obras no centro", event_id="city", topic="WORLD", country="BR")
    assert {item["event_id"] for item in briefing(repo, scope="GLOBAL")} == {"war", "truce"}
    assert {item["event_id"] for item in briefing(repo, scope="LOCAL")} == {"war", "city"}


def test_feed_and_trending_show_a_portuguese_reader_only_portuguese_coverage(repo):
    from conftest import add_user
    from newzi_backend.trending import trending_events
    add_user(repo, "reader", topics=("WORLD",))
    repo.db.execute("UPDATE user_preferences SET country_scope='GLOBAL' WHERE user_id='reader'"); repo.db.commit()
    now = NOW
    for position, source in enumerate(("reuters", "ap", "bbc_world")):
        index(repo, f"en_{source}", source, "Earthquake shakes the capital", event_id="quake", topic="WORLD", language="en", hours_ago=position + 1)
    index(repo, "g1_peace", "g1_mundo", "Acordo de paz é assinado", event_id="peace", topic="WORLD", country="BR")
    index(repo, "uol_local", "uol", "Trânsito lento na marginal", event_id="traffic", topic="WORLD", country="BR")
    assert [item["id"] for item in repo.latest_news("reader")] == ["g1_peace"]
    assert trending_events(repo, "GLOBAL", now=now + timedelta(minutes=1), language="pt-BR") == []
    assert [event["event_id"] for event in trending_events(repo, "GLOBAL", now=now + timedelta(minutes=1), language="en")] == ["quake"]


def test_breaking_news_in_english_only_never_reaches_a_portuguese_reader():
    from newzi_backend.breaking import BreakingNewsService
    english = [{"source_country": "US", "source_id": f"s{n}", "source_language": "en"} for n in range(5)]
    event = {"articles": english, "topics": {"WORLD"}}
    prefs = {"content_scope": "all", "country_scope": "GLOBAL"}
    assert not BreakingNewsService.matches({**prefs, "language": "pt-BR"}, event)
    assert BreakingNewsService.matches({**prefs, "language": "en"}, event)
    portuguese = {"source_country": "BR", "source_id": "g1_mundo", "source_language": "pt-BR"}
    assert BreakingNewsService.matches({**prefs, "language": "pt-BR"}, {**event, "articles": [*english, portuguese]})


def test_portuguese_audio_skips_a_foreign_story_it_cannot_translate():
    from newzi_backend.audio import AudioScriptComposer
    edition = {"status": "READY", "language": "pt-BR", "items": [
        {"id": "i1", "headline": "Storm hits the coast", "summary": "A strong storm hit the coast on Monday morning, officials said.",
         "warnings": ["SOURCE_LANGUAGE_FALLBACK"]},
        {"id": "i2", "headline": "Parlamento aprova orçamento", "summary": "O Parlamento aprovou nesta segunda o orçamento do próximo ano.",
         "warnings": []}]}

    class Broken:
        def translate(self, fields, language): raise RuntimeError("model crashed")
    for translator in (None, Broken()):
        segments = AudioScriptComposer(translator=translator).compose(edition, "pt-BR")
        assert [item_id for kind, item_id, _ in segments if kind == "ITEM"] == ["i2"]
        assert "storm" not in " ".join(text for *_, text in segments).lower()
