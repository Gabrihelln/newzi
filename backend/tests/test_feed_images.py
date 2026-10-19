"""Story pictures: photos carried inside the feed text, the enrichment queue's priority and paused sites."""
from datetime import datetime, timedelta, timezone

import httpx


def article(article_id, url, image_url=None, hours_ago=1):
    from newzi_engine.models import Article
    published = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return Article(article_id, "src", "Src", "Título " + article_id, "", url, url, published, published, "pt-BR",
                   image_url=image_url, image_source="rss:media:content" if image_url else None)


def test_a_photo_inside_the_feed_description_is_the_story_picture():
    from newzi_engine.images import extract_feed_image
    entry = {"summary": '<p><img class="wp-post-image" src="https://cdn.contigo.com.br/2026/10/atriz.jpg" alt=""> A atriz falou.</p>'}
    assert extract_feed_image(entry, "https://contigo.com.br/x") == ("https://cdn.contigo.com.br/2026/10/atriz.jpg", "rss:inline-image")
    # A proper Media RSS picture still wins, and logos inside the text are not photos.
    entry["media_content"] = [{"url": "https://cdn.contigo.com.br/2026/10/capa.jpg", "medium": "image"}]
    assert extract_feed_image(entry, "https://contigo.com.br/x")[1] == "rss:media:content"
    assert extract_feed_image({"summary": '<img src="https://contigo.com.br/logo.png">'}, "https://contigo.com.br/x") == (None, None)


def test_an_empty_feed_response_is_a_failure_not_an_empty_feed(monkeypatch):
    from newzi_engine.collectors import rss
    transport = httpx.MockTransport(lambda request: httpx.Response(202, content=b""))
    monkeypatch.setattr(rss.httpx, "stream", lambda method, url, **kwargs: httpx.Client(transport=transport).stream(method, url, headers=kwargs.get("headers")))
    collector = rss.RSSCollector({})
    batch, error = collector.collect({"id": "espn_brasil", "name": "ESPN Brasil", "feed_url": "https://www.espn.com.br/rss"})
    assert batch == [] and error == "empty feed response (HTTP 202)" and collector.last_metrics["status"] == "FAILED"


def test_stories_without_a_picture_come_first_in_the_enrichment_queue(tmp_path):
    from newzi_engine.storage import Store
    store = Store(tmp_path / "engine.sqlite3")
    store.upsert_articles([article("with_photo_new", "https://g1.globo.com/a", "https://s2.glbimg.com/a.jpg", hours_ago=1),
                           article("no_photo_old", "https://www1.folha.uol.com.br/b", hours_ago=5)])
    assert [item.article_id for item in store.articles_needing_image(1)] == ["no_photo_old"]


def test_a_site_that_keeps_blocking_is_paused_and_its_stories_keep_their_feed_picture(tmp_path, monkeypatch):
    from newzi_engine import images
    from newzi_engine.storage import IMAGE_HOST_FAILURES_BEFORE_PAUSE, Store
    store = Store(tmp_path / "engine.sqlite3")
    for _ in range(IMAGE_HOST_FAILURES_BEFORE_PAUSE - 1):
        store.record_image_host("www.poder360.com.br", False)
    assert not store.image_host_paused("www.poder360.com.br")
    store.record_image_host("www.poder360.com.br", False)
    assert store.image_host_paused("www.poder360.com.br")
    store.record_image_host("g1.globo.com", False); store.record_image_host("g1.globo.com", True)
    assert not store.image_host_paused("g1.globo.com")

    store.upsert_articles([article("p1", "https://www.poder360.com.br/p1"),
                           article("p2", "https://www.poder360.com.br/p2", "https://static.poder360.com.br/p2.jpg"),
                           article("g1", "https://g1.globo.com/g1")])
    fetched = []

    def resolve(item, timeout, diagnostics=None, exclude=()):
        fetched.append(item.article_id)
        diagnostics["article_pages_fetched"] = 1
        return "https://s2.glbimg.com/g1.jpg", "html:og:image"
    monkeypatch.setattr(images, "resolve_article_image", resolve)
    result = images.enrich_missing_images(store, limit=10)
    assert fetched == ["g1"] and result["paused_host_skips"] == 2
    saved = {row["article_id"]: row["image_url"] for row in store.db.execute("SELECT article_id,image_url FROM articles")}
    assert saved == {"p1": None, "p2": "https://static.poder360.com.br/p2.jpg", "g1": "https://s2.glbimg.com/g1.jpg"}
    assert store.articles_needing_image(10) == []          # all checked: the paused site does not come back next cycle
