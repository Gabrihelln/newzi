"""One timestamp format for everything the product database stores.

Timestamps are compared as strings in SQL (``scheduled_for<=?``, ``published_at>=?``), which is
only correct when every value has the same shape. All writes go through iso(), which produces
fixed-width UTC with milliseconds and a ``Z`` suffix, ``2026-10-09T13:05:00.000Z``: the
ECMAScript date format, which every JavaScript engine (Hermes included) parses.
"""
from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc)


def iso(moment):
    """Canonical text for an aware datetime (a naive one is taken as UTC); None stays None."""
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    moment = moment.astimezone(timezone.utc)
    return f"{moment:%Y-%m-%dT%H:%M:%S}.{moment.microsecond // 1000:03d}Z"


def now_iso():
    return iso(utc_now())


def parse(value):
    """Aware datetime from any ISO-8601 text this codebase has ever stored."""
    if value is None:
        return None
    if isinstance(value, datetime):
        moment = value
    else:
        moment = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00").replace(" ", "T", 1))
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def normalize(value):
    """Canonical form of a stored timestamp; values that are not timestamps are returned unchanged."""
    if not value or not isinstance(value, str) or len(value) < 19 or value[10] not in "T ":
        return value
    try:
        return iso(parse(value))
    except ValueError:
        return value
