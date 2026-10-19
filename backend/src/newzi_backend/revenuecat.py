"""RevenueCat: the store purchases (App Store, later Google Play) that make an account Premium.

The app logs into RevenueCat with the backend user id, so every RevenueCat ``app_user_id`` is a ``users.id``.

- Webhook (POST /api/v1/webhooks/revenuecat): RevenueCat calls it on every purchase, renewal, cancellation,
  billing issue, expiration or refund. The request must carry ``Authorization: <REVENUECAT_WEBHOOK_AUTH>``, the
  value typed in the RevenueCat dashboard; without that setting the webhook is off.
- Sync (POST /api/v1/me/subscription/sync): the app calls it right after a purchase or a restore, so Premium opens
  without waiting for the webhook.

Both read the subscriber from RevenueCat's REST API (REVENUECAT_SECRET_KEY, a secret ``sk_`` key) and write the
``subscriptions`` row from it, so the row always matches what RevenueCat knows, whatever the order the events
arrive in. Without the secret key the webhook falls back to the event's own fields.
"""
import logging
import os
from datetime import datetime, timezone

import httpx

from .timeutil import iso

log = logging.getLogger("news_engine.product")

ENTITLEMENT = "premium"
API = "https://api.revenuecat.com/v1"
STORES = {"APP_STORE": "app_store", "MAC_APP_STORE": "app_store", "PLAY_STORE": "google_play", "app_store": "app_store",
          "mac_app_store": "app_store", "play_store": "google_play"}


def webhook_auth():
    return (os.getenv("REVENUECAT_WEBHOOK_AUTH") or "").strip()


def secret_key():
    return (os.getenv("REVENUECAT_SECRET_KEY") or "").strip()


def _period(product_id):
    return "annual" if "annual" in (product_id or "").lower() or "anual" in (product_id or "").lower() else "monthly"


def _ms(value):
    return iso(datetime.fromtimestamp(value / 1000, timezone.utc)) if value else None


def _date(value):
    """RevenueCat dates (``2026-10-20T12:00:00Z``) in the database format."""
    if not value:
        return None
    return iso(datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc))


def _user_exists(repo, uid):
    return bool(uid) and repo.db.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone() is not None


def write(repo, uid, *, product_id, store, started_at, expires_at, billing_issue, unsubscribed, now=None):
    """Store the plan RevenueCat reports for ``uid`` (one row per user)."""
    now = iso(now or datetime.now(timezone.utc))
    if expires_at and expires_at <= now:
        status = "expired"
    elif billing_issue:
        status = "grace"
    elif unsubscribed:
        status = "canceled"
    else:
        status = "active"
    repo.db.execute("""INSERT INTO subscriptions(user_id,period,status,store,product_id,purchase_token,started_at,expires_at,auto_renew,updated_at)
        VALUES(?,?,?,?,?,NULL,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET period=excluded.period,status=excluded.status,
        store=excluded.store,product_id=excluded.product_id,started_at=excluded.started_at,expires_at=excluded.expires_at,
        auto_renew=excluded.auto_renew,updated_at=excluded.updated_at""",
        (uid, _period(product_id), status, store, product_id, started_at, expires_at or now, 0 if unsubscribed else 1, now))
    repo.db.commit()
    log.info("[Billing] subscription user=%s product=%s status=%s expires=%s", uid, product_id, status, expires_at)
    return status


def fetch_subscriber(uid, client=None):
    """The subscriber RevenueCat knows for ``uid`` (REST API v1), or None without a secret key."""
    key = secret_key()
    if not key:
        return None
    own = client is None
    client = client or httpx.Client(timeout=15)
    try:
        response = client.get(f"{API}/subscribers/{uid}", headers={"Authorization": f"Bearer {key}"})
        response.raise_for_status()
        return response.json().get("subscriber") or {}
    finally:
        if own:
            client.close()


def apply_subscriber(repo, uid, subscriber, now=None):
    """Write the ``premium`` entitlement of a RevenueCat subscriber; returns the status, or None without one."""
    entitlement = (subscriber.get("entitlements") or {}).get(ENTITLEMENT)
    if not entitlement:
        return None
    product_id = entitlement.get("product_identifier")
    details = (subscriber.get("subscriptions") or {}).get(product_id) or {}
    return write(repo, uid, product_id=product_id, store=STORES.get(details.get("store") or "", "app_store"),
                 started_at=_date(entitlement.get("purchase_date")), expires_at=_date(entitlement.get("expires_date")),
                 billing_issue=bool(details.get("billing_issues_detected_at")) and not details.get("unsubscribe_detected_at"),
                 unsubscribed=bool(details.get("unsubscribe_detected_at")), now=now)


def sync(repo, uid, client=None, now=None):
    """Bring the user's row up to date with RevenueCat (after a purchase or a restore in the app)."""
    try:
        subscriber = fetch_subscriber(uid, client)
    except httpx.HTTPError as exc:
        log.warning("[Billing] sync_failed user=%s error=%s", uid, exc)
        return None
    return None if subscriber is None else apply_subscriber(repo, uid, subscriber, now)


def apply_event(repo, event, now=None):
    """Fallback without the secret key: the plan straight from a webhook event."""
    kind = event.get("type")
    if ENTITLEMENT not in (event.get("entitlement_ids") or [ENTITLEMENT]):
        return None
    if kind in ("TEST", "TRANSFER", "SUBSCRIBER_ALIAS", "NON_RENEWING_PURCHASE", "TEMPORARY_ENTITLEMENT_GRANT", "SUBSCRIPTION_EXTENDED_IGNORED"):
        return None
    expires_at = _ms(event.get("expiration_at_ms"))
    if kind == "EXPIRATION" or (kind == "CANCELLATION" and event.get("cancel_reason") == "CUSTOMER_SUPPORT"):
        expires_at = iso(now or datetime.now(timezone.utc))   # expired, or refunded: no access from now on
    return write(repo, event.get("app_user_id"), product_id=event.get("product_id"), store=STORES.get(event.get("store") or "", "app_store"),
                 started_at=_ms(event.get("purchased_at_ms")), expires_at=expires_at, billing_issue=kind == "BILLING_ISSUE",
                 unsubscribed=kind == "CANCELLATION", now=now)


def handle_webhook(repo, authorization, body, client=None, now=None):
    """A RevenueCat webhook call: ``(http_status, response_body)``."""
    expected = webhook_auth()
    if not expected:
        return 503, {"status": "disabled"}
    if (authorization or "").strip() not in (expected, f"Bearer {expected}"):
        return 401, {"status": "unauthorized"}
    event = body.get("event") or {}
    # A purchase can name the user under an alias (the anonymous id before logIn); pick the one we know.
    candidates = [event.get("app_user_id"), event.get("original_app_user_id"), *(event.get("aliases") or [])]
    uid = next((item for item in candidates if _user_exists(repo, item)), None)
    log.info("[Billing] webhook type=%s user=%s environment=%s", event.get("type"), uid, event.get("environment"))
    if not uid:
        return 200, {"status": "ignored"}       # anonymous or unknown user: nothing to write, never retry
    if not secret_key():
        return 200, {"status": apply_event(repo, {**event, "app_user_id": uid}, now) or "ignored"}
    try:
        subscriber = fetch_subscriber(uid, client)
    except httpx.HTTPError as exc:
        log.warning("[Billing] webhook_sync_failed user=%s error=%s", uid, exc)
        return 503, {"status": "retry"}         # RevenueCat retries a failed delivery
    return 200, {"status": apply_subscriber(repo, uid, subscriber, now) or "ignored"}
