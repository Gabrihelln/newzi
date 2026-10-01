"""Restricted WebP-to-JPEG transport for stored article images on iOS."""
from __future__ import annotations

import ipaddress
import socket
from functools import lru_cache
from io import BytesIO
from urllib.parse import urljoin, urlsplit

import httpx
from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 30_000_000
MAX_REDIRECTS = 3
ALLOWED_IMAGE_HOSTS = {
    "tl.ctcdn.com.br": ("/",),
    "storage.googleapis.com": ("/gweb-uniblog-publish-prod/",),
    "techcrunch.com": ("/wp-content/uploads/",),
}


class ArticleImageError(ValueError):
    """The stored article image cannot be safely delivered to mobile."""


def needs_webp_proxy(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlsplit(url)
    return parsed.path.lower().endswith(".webp") or "format(webp)" in parsed.path.lower() or "format=webp" in parsed.query.lower()


def _validate_stored_url(url: str, expected_host: str | None = None) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https" or not host or parsed.username or parsed.password:
        raise ArticleImageError("unsupported image URL")
    if parsed.port not in (None, 443) or host not in ALLOWED_IMAGE_HOSTS:
        raise ArticleImageError("image host is not permitted")
    if expected_host and host != expected_host:
        raise ArticleImageError("image redirect host is not permitted")
    if not any(parsed.path.startswith(prefix) for prefix in ALLOWED_IMAGE_HOSTS[host]):
        raise ArticleImageError("image path is not permitted")
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ArticleImageError("image host lookup failed") from exc
    if not addresses:
        raise ArticleImageError("image host lookup failed")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address[4][0])
        except ValueError as exc:
            raise ArticleImageError("invalid image host address") from exc
        if not ip.is_global:
            raise ArticleImageError("image host resolved to a non-public address")
    return host


@lru_cache(maxsize=8)
def _fetch_and_transcode(url: str) -> bytes:
    expected_host = _validate_stored_url(url)
    headers = {
        "Accept": "image/webp",
        "User-Agent": "NEWZI/1.0 (+stored article image)",
    }
    current = url
    with httpx.Client(timeout=httpx.Timeout(5.0, connect=2.0), follow_redirects=False) as client:
        for redirect_count in range(MAX_REDIRECTS + 1):
            _validate_stored_url(current, expected_host)
            with client.stream("GET", current, headers=headers) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location")
                    if not location or redirect_count == MAX_REDIRECTS:
                        raise ArticleImageError("image redirect limit exceeded")
                    current = urljoin(current, location)
                    continue
                if response.status_code != 200:
                    raise ArticleImageError("image server returned an unusable status")
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if content_type != "image/webp":
                    raise ArticleImageError("stored image is not WebP")
                length = response.headers.get("Content-Length")
                if length:
                    try:
                        if int(length) <= 0 or int(length) > MAX_IMAGE_BYTES:
                            raise ArticleImageError("image exceeds size limit")
                    except ValueError as exc:
                        raise ArticleImageError("invalid image size") from exc
                raw = bytearray()
                for chunk in response.iter_bytes(64 * 1024):
                    raw.extend(chunk)
                    if len(raw) > MAX_IMAGE_BYTES:
                        raise ArticleImageError("image exceeds size limit")
                break
        else:
            raise ArticleImageError("image redirect limit exceeded")

    try:
        with Image.open(BytesIO(raw)) as source:
            if source.format != "WEBP" or source.width * source.height > MAX_IMAGE_PIXELS:
                raise ArticleImageError("image dimensions or format are not supported")
            source.load()
            image = source.convert("RGB")
            output = BytesIO()
            image.save(output, format="JPEG", quality=86, optimize=True)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ArticleImageError("image could not be decoded") from exc


def load_article_image(url: str) -> bytes:
    if not needs_webp_proxy(url):
        raise ArticleImageError("only WebP article images use this endpoint")
    try:
        return _fetch_and_transcode(url)
    except httpx.HTTPError as exc:
        raise ArticleImageError("image source is unavailable") from exc
