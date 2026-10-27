"""Sales numbers for the panel's Assinaturas screen (Etapa 3 of docs/ANALYTICS_NEWZI.md).

Two sources:

- ``billing_events``: every RevenueCat webhook event since the panel shipped (revenuecat.py). Gives trials,
  conversions, new subscriptions, renewals, cancellations, refunds and revenue per day, in the purchase currency.
  Sandbox purchases (TestFlight, review) are left out unless asked for.
- RevenueCat's overview metrics (API v2: MRR, active subscriptions and trials, revenue of the last 28 days), when
  REVENUECAT_API_V2_KEY (a read-only v2 secret key with the "charts metrics" permission) and REVENUECAT_PROJECT_ID
  are set. Cached for ten minutes; a failure only hides that block.
"""
import os
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import httpx

from .admin import analytics_zone, local_day
from .timeutil import iso, parse

API_V2 = "https://api.revenuecat.com/v2"
CACHE_SECONDS = 600
REVENUE_TYPES = ("INITIAL_PURCHASE", "RENEWAL", "NON_RENEWING_PURCHASE", "PRODUCT_CHANGE")
_cache = {"at": 0.0, "value": None}


def _classify(event):
    """The panel's name for a RevenueCat event, or None for the ones it does not count."""
    kind, trial = event["type"], (event["period_type"] or "").upper() == "TRIAL"
    if kind == "INITIAL_PURCHASE":
        return "trial_started" if trial else "new_paid"
    if kind == "RENEWAL":
        return "trial_converted" if event["is_trial_conversion"] else "renewal"
    if kind == "CANCELLATION":
        if event["cancel_reason"] == "CUSTOMER_SUPPORT":
            return "refund"
        return "trial_cancelled" if trial else "cancellation"
    return {"UNCANCELLATION": "uncancellation", "EXPIRATION": "expiration", "BILLING_ISSUE": "billing_issue",
            "PRODUCT_CHANGE": "product_change", "NON_RENEWING_PURCHASE": "new_paid"}.get(kind)


def _money(event):
    """Gross amount of the event in its own currency (negative for a refund), or None."""
    amount = event["price_local"] if event["price_local"] is not None else event["price_usd"]
    currency = event["currency"] if event["price_local"] is not None else "USD"
    if amount is None or not currency:
        return None
    if event["type"] == "CANCELLATION" and event["cancel_reason"] == "CUSTOMER_SUPPORT":
        return currency, -abs(amount)
    if event["type"] in REVENUE_TYPES and amount > 0:
        return currency, amount
    return None


def sales(repo, days=30, include_sandbox=False, now=None):
    now = now or datetime.now(timezone.utc)
    days = max(1, min(int(days or 30), 365))
    today = datetime.fromisoformat(local_day(now)).date()
    window = [(today - timedelta(days=offset)).isoformat() for offset in range(days - 1, -1, -1)]
    since = iso(datetime(*map(int, window[0].split("-")), tzinfo=analytics_zone()))
    environment = "" if include_sandbox else "AND (environment IS NULL OR environment<>'SANDBOX')"
    rows = [dict(row) for row in repo.db.execute(f"""SELECT b.*,u.email FROM billing_events b LEFT JOIN users u ON u.id=b.user_id
        WHERE b.event_at>=? {environment} ORDER BY b.event_at DESC""", (since,)).fetchall()]
    totals, per_day = Counter(), {day: Counter() for day in window}
    revenue, net, revenue_per_day = defaultdict(float), defaultdict(float), {day: defaultdict(float) for day in window}
    for row in rows:
        name = _classify(row)
        day = local_day(parse(row["event_at"]))
        row["kind"] = name
        if name:
            totals[name] += 1
            if day in per_day:
                per_day[day][name] += 1
        money = _money(row)
        if money:
            currency, amount = money
            revenue[currency] += amount
            # Without the store's share in the event, 70% is the usual take-home.
            net[currency] += amount * (row["takehome"] if row["takehome"] is not None else 0.7)
            if day in revenue_per_day:
                revenue_per_day[day][currency] += amount
    trials = totals["trial_started"]
    return {
        "days": days,
        "include_sandbox": include_sandbox,
        "since_events": repo.db.execute("SELECT MIN(event_at) FROM billing_events").fetchone()[0],
        "totals": dict(totals),
        "trial_conversion": {"started": trials, "converted": totals["trial_converted"], "cancelled": totals["trial_cancelled"]},
        "revenue": {currency: round(value, 2) for currency, value in revenue.items()},
        "net_estimate": {currency: round(value, 2) for currency, value in net.items()},
        "per_day": [{"day": day, **per_day[day], "revenue": {c: round(v, 2) for c, v in revenue_per_day[day].items()}} for day in window],
        "events": rows[:200],
        "overview": overview(),
    }


def overview(client=None, force=False):
    """RevenueCat's overview metrics, or a dict saying why they are missing."""
    key, project = os.getenv("REVENUECAT_API_V2_KEY", "").strip(), os.getenv("REVENUECAT_PROJECT_ID", "").strip()
    if not key or not project:
        return {"configured": False}
    if not force and _cache["value"] is not None and time.monotonic() - _cache["at"] < CACHE_SECONDS:
        return _cache["value"]
    own = client is None
    client = client or httpx.Client(timeout=15)
    try:
        response = client.get(f"{API_V2}/projects/{project}/metrics/overview", headers={"Authorization": f"Bearer {key}"},
                              params={"currency": os.getenv("REVENUECAT_CURRENCY", "BRL")})
        response.raise_for_status()
        metrics = [{key: item.get(key) for key in ("id", "name", "description", "unit", "period", "value", "last_updated_at")}
                   for item in response.json().get("metrics") or []]
        value = {"configured": True, "metrics": metrics, "fetched_at": iso(datetime.now(timezone.utc))}
    except (httpx.HTTPError, ValueError) as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        value = {"configured": True, "error": f"RevenueCat respondeu {status}" if status else type(exc).__name__}
    finally:
        if own:
            client.close()
    _cache.update(at=time.monotonic(), value=value)
    return value
