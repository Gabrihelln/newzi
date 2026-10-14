"""Per-source collection health: is each configured feed fetching, and is it still publishing?"""
import json
from datetime import datetime, timedelta, timezone

from newzi_engine.collectors.registry import load_sources
from newzi_engine.storage import Store

from .timeutil import iso, parse

# Ordered from worst to best; the report lists sources in this order.
STATUSES = ("BROKEN", "FAILING", "DEGRADED", "SILENT", "OK", "DISABLED")
SILENT_AFTER = timedelta(hours=72)


def _status(source, health, latest, now):
    if not source.get("enabled", True):
        return "DISABLED"
    failures = int(health.get("consecutive_failures") or 0)
    if failures >= 3:
        # A feed that never answered once is misconfigured (moved URL, blocked), not having a bad day.
        return "BROKEN" if not health.get("last_success_at") else "FAILING"
    if failures:
        return "DEGRADED"
    if health.get("last_success_at") and (not latest or now - latest > SILENT_AFTER):
        return "SILENT"
    return "OK" if health else "SILENT"


def _diagnosis(status, metrics):
    """A plain reason an operator can act on: fix the URL, replace the feed, or wait."""
    http = metrics.get("http_status")
    if status in ("BROKEN", "FAILING", "DEGRADED"):
        return {404: "FEED_URL_NOT_FOUND", 410: "FEED_URL_NOT_FOUND", 401: "ACCESS_BLOCKED", 403: "ACCESS_BLOCKED",
                429: "RATE_LIMITED"}.get(http, "SERVER_ERROR" if http and http >= 500 else "FETCH_FAILED")
    if status == "SILENT":
        items, too_old = metrics.get("feed_items"), metrics.get("items_too_old")
        if items == 0:
            return "FEED_EMPTY"
        if items and too_old == items:
            return "FEED_ABANDONED"      # every item is older than the collection window
        return "NO_RECENT_ITEMS"
    return None


def source_health_report(repo, now=None, store=None):
    now = now or datetime.now(timezone.utc)
    health = (store or Store()).get_source_health()
    day, week = iso(now - timedelta(hours=24)), iso(now - timedelta(days=7))
    counts = {row["source_id"]: row for row in repo.db.execute(
        """SELECT source_id, SUM(CASE WHEN published_at>=? THEN 1 ELSE 0 END) AS day,
                  SUM(CASE WHEN published_at>=? THEN 1 ELSE 0 END) AS week, MAX(published_at) AS latest
           FROM indexed_content GROUP BY source_id""", (day, week))}
    rows = []
    for source in load_sources():
        state = health.get(source["id"], {})
        indexed = counts.get(source["id"])
        latest = parse(indexed["latest"]) if indexed and indexed["latest"] else None
        metrics = json.loads(state.get("last_metrics_json") or "{}")
        error = str(state.get("last_error") or "").strip().splitlines()
        status = _status(source, state, latest, now)
        rows.append({
            "id": source["id"], "name": source.get("name"), "status": status,
            "diagnosis": _diagnosis(status, metrics), "feed_url": source.get("feed_url"),
            "feed_newest_item": metrics.get("feed_newest_item"),
            "consecutive_failures": int(state.get("consecutive_failures") or 0),
            "http_status": metrics.get("http_status"), "last_error": error[0][:200] if error else None,
            "last_success_at": state.get("last_success_at"), "circuit_open_until": state.get("circuit_open_until"),
            "average_duration_ms": round(float(state.get("average_duration_ms") or 0)),
            "articles_24h": int(indexed["day"] or 0) if indexed else 0,
            "articles_7d": int(indexed["week"] or 0) if indexed else 0,
            "latest_article_at": iso(latest) if latest else None})
    rows.sort(key=lambda row: (STATUSES.index(row["status"]), row["id"]))
    summary = {status: sum(row["status"] == status for row in rows) for status in STATUSES}
    return {"status": "degraded" if summary["BROKEN"] or summary["FAILING"] else "ok",
            "generated_at": iso(now), "summary": summary, "sources": rows}
