"""Best-effort extraction and validation of article-specific image metadata."""
from __future__ import annotations

import json
import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx


_logger = logging.getLogger(__name__)
_MAX_IMAGE_PROBE_BYTES = 4096
_MAX_ARTICLE_IMAGE_CANDIDATES = 3
_MAX_IMAGE_REDIRECTS = 5


IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif", ".svg")
_LOGO_SEGMENTS = {"favicon", "favicons", "logo", "logos", "branding", "avatar", "avatars", "placeholder"}
_GENERIC_IMAGE_SEGMENTS = {"category-image", "category-photo", "generic", "default-images", "random-images"}


def canonical_image_url(candidate, base_url=""):
    """Return a safe absolute HTTP(S) image URL or None for invalid/generic art."""
    if not isinstance(candidate, str) or not candidate.strip():
        return None
    value = unescape(candidate.strip()).replace("&amp;", "&")
    if value.startswith(("data:", "blob:", "javascript:")):
        return None
    absolute = urljoin(base_url, value)
    try:
        parsed = urlsplit(absolute)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return None
        host = parsed.hostname.lower()
        path = parsed.path
        query = parsed.query
        # The Guardian's auto=format negotiation can return a remote WebP/AVIF
        # even though the stored path ends in .jpg. Keep the publisher's JPEG
        # rendition so iOS and Android receive a format React Native decodes.
        if host == "i.guim.co.uk":
            query_parts = [part for part in query.split("&") if part.partition("=")[0].lower() != "auto"]
            query = "&".join(query_parts)
        if re.search(r"(?:\.avif(?:$|[?#])|format\(avif\))", path + "?" + query, re.IGNORECASE):
            return None
        if path != parsed.path or query != parsed.query:
            absolute = urlunsplit((parsed.scheme, parsed.netloc, path, query, parsed.fragment))
            parsed = urlsplit(absolute)
        path_parts = [part.lower() for part in parsed.path.split("/") if part]
        if any(part in _LOGO_SEGMENTS or part in _GENERIC_IMAGE_SEGMENTS for part in path_parts):
            return None
        file_name = path_parts[-1] if path_parts else ""
        if file_name.startswith(("favicon.", "logo.", "placeholder.")):
            return None
        image_stem = file_name.rsplit(".", 1)[0]
        if re.fullmatch(r"(?:new-(?:reading|waving|sunrise|celebrate)|mascot|article-fallback|category-(?:image|photo)(?:-[a-z0-9_-]+)?|generic|default-image|random)", image_stem):
            return None
        if re.search(r"(?:^|[/_-])(?:pixel|spacer|tracking)(?:[._/?-]|$)", parsed.path.lower()):
            return None
        query = dict(part.split("=", 1) if "=" in part else (part, "") for part in parsed.query.lower().split("&") if part)
        if any(query.get(key) == "1" for key in ("w", "width", "h", "height")) and query.get("w", query.get("width")) == "1" and query.get("h", query.get("height")) == "1":
            return None
        return absolute
    except (ValueError, UnicodeError):
        return None


def _values(value):
    if isinstance(value, (list, tuple)):
        yield from value
    elif value is not None:
        yield value


def _candidate_from_record(record):
    if isinstance(record, str):
        return record
    if not isinstance(record, dict):
        return None
    media_type = str(record.get("type") or "").lower()
    medium = str(record.get("medium") or "").lower()
    if media_type and not media_type.startswith("image/"):
        return None
    if medium and medium != "image":
        return None
    return record.get("url") or record.get("href") or record.get("src")


def feed_image_candidates(entry, article_url=""):
    """Yield article-scoped RSS/Atom image metadata in the preferred order."""
    for key, source in (("media_content", "rss:media:content"), ("media_thumbnail", "rss:media:thumbnail"), ("enclosures", "rss:enclosure"), ("links", "rss:link-enclosure")):
        records = entry.get(key) or []
        for record in _values(records):
            if key == "links" and (record.get("rel") != "enclosure" if isinstance(record, dict) else True):
                continue
            candidate = _candidate_from_record(record)
            if candidate:
                normalized = canonical_image_url(candidate, article_url)
                if normalized:
                    yield normalized, source
    image = entry.get("image")
    if isinstance(image, dict):
        candidate = image.get("href") or image.get("url")
        normalized = canonical_image_url(candidate, article_url)
        if normalized:
            yield normalized, "rss:entry-image"


def extract_feed_image(entry, article_url=""):
    return next(feed_image_candidates(entry, article_url), (None, None))


class _ArticleMetadataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = []
        self.jsonld = []
        self._inside_jsonld = False
        self._script_text = []

    def handle_starttag(self, tag, attrs):
        values = {str(key).lower(): value for key, value in attrs if key}
        if tag.lower() == "meta":
            key = (values.get("property") or values.get("name") or values.get("itemprop") or "").lower()
            content = values.get("content")
            if content:
                self.meta.append((key, content))
        elif tag.lower() == "link" and "image_src" in str(values.get("rel", "")).lower():
            if values.get("href"):
                self.meta.append(("link:image_src", values["href"]))
        elif tag.lower() == "script" and "ld+json" in str(values.get("type", "")).lower():
            self._inside_jsonld = True
            self._script_text = []

    def handle_data(self, data):
        if self._inside_jsonld:
            self._script_text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self._inside_jsonld:
            self.jsonld.append("".join(self._script_text))
            self._inside_jsonld = False
            self._script_text = []


def _jsonld_images(value, depth=0):
    if depth > 10:
        return
    if isinstance(value, list):
        for item in value:
            yield from _jsonld_images(item, depth + 1)
    elif isinstance(value, dict):
        for key in ("image", "thumbnailUrl", "thumbnailURL"):
            if key in value:
                image = value[key]
                if isinstance(image, str):
                    yield image
                elif isinstance(image, dict):
                    for url_key in ("url", "contentUrl", "thumbnailUrl"):
                        if isinstance(image.get(url_key), str):
                            yield image[url_key]
                elif isinstance(image, list):
                    yield from _jsonld_images(image, depth + 1)
        for key, child in value.items():
            if key not in {"logo", "publisher"} and isinstance(child, (dict, list)):
                yield from _jsonld_images(child, depth + 1)


def article_page_image_candidates(document, article_url):
    parser = _ArticleMetadataParser()
    try:
        parser.feed(document)
    except (ValueError, AssertionError):
        return
    preferred = ("og:image", "og:image:secure_url", "twitter:image", "twitter:image:src", "image", "link:image_src")
    for key in preferred:
        for meta_key, value in parser.meta:
            if meta_key == key:
                normalized = canonical_image_url(value, article_url)
                if normalized:
                    yield normalized, "html:" + key
    for raw in parser.jsonld:
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for candidate in _jsonld_images(parsed):
            normalized = canonical_image_url(candidate, article_url)
            if normalized:
                yield normalized, "jsonld:image"


def extract_article_page_image(document, article_url):
    return next(article_page_image_candidates(document, article_url), (None, None))


def _one_pixel(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return int.from_bytes(data[16:20], "big") == 1 and int.from_bytes(data[20:24], "big") == 1
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        return int.from_bytes(data[6:8], "little") == 1 and int.from_bytes(data[8:10], "little") == 1
    if data.startswith(b"\xff\xd8"):
        offset = 2
        while offset + 9 < len(data):
            if data[offset] != 0xFF:
                offset += 1
                continue
            marker = data[offset + 1]
            length = int.from_bytes(data[offset + 2:offset + 4], "big")
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF) and length >= 7:
                return int.from_bytes(data[offset + 5:offset + 7], "big") == 1 and int.from_bytes(data[offset + 7:offset + 9], "big") == 1
            if length < 2:
                break
            offset += 2 + length
    return False


def validate_image_response(status_code, content_type, content_length=None, initial_bytes=b"", content_range=None):
    """Validate a small probe result without failing article collection."""
    try:
        media_type = str(content_type or "").lower().split(";", 1)[0]
        if int(status_code) not in (200, 206) or not media_type.startswith("image/") or media_type == "image/avif":
            return False
        if content_length is not None and int(content_length) <= 0:
            return False
        if int(status_code) == 206:
            match = re.fullmatch(r"bytes\s+(\d+)-(\d+)/(?:\d+|\*)", str(content_range or "").strip(), re.IGNORECASE)
            if not match or int(match.group(1)) != 0:
                return False
            if content_length is not None and int(content_length) != int(match.group(2)) + 1:
                return False
    except (TypeError, ValueError):
        return False
    return bool(initial_bytes) and not _one_pixel(initial_bytes)


def _timeout_budget(timeout):
    if isinstance(timeout, httpx.Timeout):
        return float(timeout.read or timeout.connect or 2.5)
    return max(0.05, float(timeout))


def _make_async_client(timeout):
    return httpx.AsyncClient(timeout=timeout, follow_redirects=True, max_redirects=_MAX_IMAGE_REDIRECTS)


def _make_sync_client(timeout):
    return httpx.Client(timeout=timeout, follow_redirects=True, max_redirects=_MAX_IMAGE_REDIRECTS)


async def _probe_image_request(client, url):
    headers = {"User-Agent": "NEWZI/1.0 (+article image metadata)", "Accept-Encoding": "identity", "Range": f"bytes=0-{_MAX_IMAGE_PROBE_BYTES - 1}"}
    async with client.stream("GET", url, headers=headers) as response:
        if response.status_code not in (200, 206):
            return False
        content_range = response.headers.get("Content-Range")
        content_length = response.headers.get("Content-Length")
        # Read at most the requested prefix. The caller's asyncio deadline covers
        # DNS/connect/headers/body and cancels a server that trickles bytes forever.
        iterator = response.aiter_raw(chunk_size=_MAX_IMAGE_PROBE_BYTES)
        try:
            first = await anext(iterator)
        except StopAsyncIteration:
            first = b""
        return validate_image_response(response.status_code, response.headers.get("Content-Type"), content_length, first, content_range)


def _probe_image(url, timeout, *, article_id=None, source=None, diagnostics=None):
    started = time.perf_counter()
    host = urlsplit(url).hostname or ""
    budget = _timeout_budget(timeout)
    result = False
    error = None
    if diagnostics is not None:
        diagnostics["image_probe_attempts"] = diagnostics.get("image_probe_attempts", 0) + 1
    try:
        async def run_probe():
            async with _make_async_client(timeout) as client:
                return await asyncio.wait_for(_probe_image_request(client, url), timeout=budget)
        result = asyncio.run(run_probe())
        return result
    except (asyncio.TimeoutError, httpx.TimeoutException) as exc:
        error = "timeout"
        if diagnostics is not None:
            diagnostics["image_probe_timeouts"] = diagnostics.get("image_probe_timeouts", 0) + 1
        return False
    except (httpx.HTTPError, OSError, ValueError) as exc:
        error = type(exc).__name__
        return False
    finally:
        _logger.info("[IMAGE] operation=probe article_id=%s source=%s url_host=%s duration_ms=%s result=%s exception_category=%s byte_budget=%s", article_id or "-", source or "-", host, round((time.perf_counter()-started)*1000, 2), "valid" if result else "invalid", error or "-", _MAX_IMAGE_PROBE_BYTES)


def fetch_article_image(article_url, timeout_seconds=2.5, max_html_bytes=1_500_000, *, article_id=None, source=None, diagnostics=None):
    """Fetch one canonical article page and discover/verify its own image only."""
    timeout = httpx.Timeout(connect=min(1.5, timeout_seconds), read=timeout_seconds, write=timeout_seconds, pool=1.0)
    deadline = time.monotonic() + timeout_seconds
    started = time.perf_counter()
    host = urlsplit(article_url).hostname or ""
    if diagnostics is not None:
        diagnostics["article_pages_fetched"] = diagnostics.get("article_pages_fetched", 0) + 1
    try:
        with _make_sync_client(timeout) as client:
            with client.stream("GET", article_url, headers={"User-Agent": "NEWZI/1.0 (+article image metadata)", "Accept": "text/html,application/xhtml+xml;q=0.9"}) as response:
                response.raise_for_status()
                media_type = response.headers.get("Content-Type", "").lower()
                if "html" not in media_type and "xhtml" not in media_type:
                    return None, None
                chunks = []
                size = 0
                for chunk in response.iter_bytes():
                    if time.monotonic() > deadline:
                        raise TimeoutError("article image metadata exceeded its time budget")
                    size += len(chunk)
                    if size > max_html_bytes:
                        break
                    chunks.append(chunk)
                document = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
                base_url = str(response.url)
    except (httpx.HTTPError, OSError, ValueError, UnicodeError):
        _logger.info("[IMAGE] operation=article_metadata article_id=%s source=%s url_host=%s duration_ms=%s result=failed exception_category=page_fetch", article_id or "-", source or "-", host, round((time.perf_counter()-started)*1000, 2))
        return None, None
    _logger.info("[IMAGE] operation=article_metadata article_id=%s source=%s url_host=%s duration_ms=%s result=parsed response_bytes=%s", article_id or "-", source or "-", urlsplit(base_url).hostname or host, round((time.perf_counter()-started)*1000, 2), size)
    for index, (candidate, candidate_source) in enumerate(article_page_image_candidates(document, base_url)):
        if index >= _MAX_ARTICLE_IMAGE_CANDIDATES:
            break
        try:
            if _probe_image(candidate, timeout, article_id=article_id, source=source, diagnostics=diagnostics):
                return candidate, candidate_source
        except (httpx.HTTPError, OSError, ValueError):
            continue
    return None, None


def image_checked_timestamp():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def enrich_missing_images(store, limit=12, max_workers=4, timeout_seconds=2.5):
    """Enrich a bounded batch; failures are recorded and never abort ingestion."""
    candidates = store.articles_needing_image(limit)
    if not candidates:
        return {"checked": 0, "found": 0, "failed": 0, "duration_ms": 0, "updated_articles": []}
    started = time.perf_counter()
    checked = found = failed = 0
    updated = []
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def discover(article):
        diagnostics = {}
        timeout = httpx.Timeout(connect=min(1.5, timeout_seconds), read=timeout_seconds, write=timeout_seconds, pool=1.0)
        if article.image_url and article.image_source and article.image_source.startswith("rss:"):
            try:
                if _probe_image(article.image_url, timeout, article_id=article.article_id, source=article.source_name, diagnostics=diagnostics):
                    return article.image_url, article.image_source, diagnostics
            except (httpx.HTTPError, OSError, ValueError):
                pass
        result = fetch_article_image(article.url, timeout_seconds, article_id=article.article_id, source=article.source_name, diagnostics=diagnostics)
        return result[0], result[1], diagnostics

    image_probe_attempts = image_probe_timeouts = article_pages_fetched = 0
    with ThreadPoolExecutor(max_workers=max(1, min(int(max_workers), 6)), thread_name_prefix="newzi-image") as pool:
        futures = {pool.submit(discover, article): article for article in candidates}
        for future in as_completed(futures):
            article = futures[future]
            operation_started = time.perf_counter()
            try:
                url, source, diagnostics = future.result()
                exception_category = "-"
            except Exception as exc:
                url, source = None, None
                diagnostics = {}
                exception_category = type(exc).__name__
            image_probe_attempts += diagnostics.get("image_probe_attempts", 0)
            image_probe_timeouts += diagnostics.get("image_probe_timeouts", 0)
            article_pages_fetched += diagnostics.get("article_pages_fetched", 0)
            checked += 1
            failed += int(url is None)
            timestamp = image_checked_timestamp()
            store.save_article_image(article.article_id, url, source, timestamp)
            article.image_url = url
            article.image_source = source
            article.image_checked_at = timestamp
            updated.append(article)
            if url:
                found += 1
            _logger.info("[IMAGE] progress=%s/%s article_id=%s source=%s operation=enrichment url_host=%s duration_ms=%s result=%s exception_category=%s", checked, len(candidates), article.article_id, article.source_name, urlsplit(url or article.url).hostname or "", round((time.perf_counter()-operation_started)*1000, 2), "resolved" if url else "no_image", exception_category)
    return {"checked": checked, "found": found, "failed": failed, "image_probe_attempts": image_probe_attempts, "image_probe_timeouts": image_probe_timeouts, "article_pages_fetched": article_pages_fetched, "duration_ms": int((time.perf_counter() - started) * 1000), "updated_articles": updated}
