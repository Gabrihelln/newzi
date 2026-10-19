from datetime import datetime, timezone

import httpx
import pytest

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
MS = lambda value: int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp() * 1000)


@pytest.fixture()
def setup(tmp_path, monkeypatch):
    from newzi_backend.product_backend import ProductRepository
    repo = ProductRepository(tmp_path / "product.db")
    uid = repo.create_dev_user()["id"]
    monkeypatch.setenv("REVENUECAT_WEBHOOK_AUTH", "segredo")
    monkeypatch.delenv("REVENUECAT_SECRET_KEY", raising=False)
    return repo, uid


def row(repo, uid):
    return repo.db.execute("SELECT * FROM subscriptions WHERE user_id=?", (uid,)).fetchone()


def event(uid, kind, product="newzi_premium_annual", expires="2027-10-20T12:00:00", **extra):
    return {"api_version": "1.0", "event": {"type": kind, "app_user_id": uid, "product_id": product, "entitlement_ids": ["premium"],
            "store": "APP_STORE", "environment": "SANDBOX", "purchased_at_ms": MS("2026-10-20T11:00:00"), "expiration_at_ms": MS(expires), **extra}}


def test_webhook_needs_its_secret_and_ignores_unknown_users(setup, monkeypatch):
    from newzi_backend.revenuecat import handle_webhook
    repo, uid = setup
    assert handle_webhook(repo, "errado", event(uid, "INITIAL_PURCHASE"), now=NOW)[0] == 401
    assert handle_webhook(repo, None, event(uid, "INITIAL_PURCHASE"), now=NOW)[0] == 401
    assert handle_webhook(repo, "segredo", event("$RCAnonymousID:abc", "INITIAL_PURCHASE"), now=NOW) == (200, {"status": "ignored"})
    assert row(repo, uid) is None
    monkeypatch.delenv("REVENUECAT_WEBHOOK_AUTH")
    assert handle_webhook(repo, "segredo", event(uid, "INITIAL_PURCHASE"), now=NOW)[0] == 503


def test_webhook_events_drive_the_plan_without_the_secret_key(setup):
    from newzi_backend.revenuecat import handle_webhook
    from newzi_backend.subscriptions import is_premium, subscription_for
    repo, uid = setup
    assert handle_webhook(repo, "Bearer segredo", event(uid, "INITIAL_PURCHASE"), now=NOW) == (200, {"status": "active"})
    plan = subscription_for(repo, uid, NOW)
    assert plan["tier"] == "premium" and plan["period"] == "annual" and plan["will_renew"] and row(repo, uid)["store"] == "app_store"
    handle_webhook(repo, "segredo", event(uid, "BILLING_ISSUE"), now=NOW)
    assert subscription_for(repo, uid, NOW)["payment_issue"]
    handle_webhook(repo, "segredo", event(uid, "CANCELLATION", cancel_reason="UNSUBSCRIBE"), now=NOW)
    plan = subscription_for(repo, uid, NOW)
    assert plan["tier"] == "premium" and not plan["will_renew"]            # keeps Premium until the paid period ends
    handle_webhook(repo, "segredo", event(uid, "EXPIRATION"), now=NOW)
    assert not is_premium(repo, uid, NOW) and row(repo, uid)["status"] == "expired"
    # A refund through Apple support ends access at once.
    handle_webhook(repo, "segredo", event(uid, "RENEWAL", product="newzi_premium_monthly"), now=NOW)
    assert row(repo, uid)["period"] == "monthly" and is_premium(repo, uid, NOW)
    handle_webhook(repo, "segredo", event(uid, "CANCELLATION", cancel_reason="CUSTOMER_SUPPORT"), now=NOW)
    assert not is_premium(repo, uid, NOW)


def test_webhook_finds_the_user_under_an_alias(setup):
    from newzi_backend.revenuecat import handle_webhook
    repo, uid = setup
    body = event("$RCAnonymousID:abc", "INITIAL_PURCHASE", aliases=["$RCAnonymousID:abc", uid])
    assert handle_webhook(repo, "segredo", body, now=NOW) == (200, {"status": "active"})
    assert row(repo, uid)["status"] == "active"


def subscriber_client(expires="2027-10-20T12:00:00Z", unsubscribed=None, fail=False):
    def answer(request):
        if fail:
            return httpx.Response(500)
        assert request.headers["authorization"] == "Bearer sk_teste"
        return httpx.Response(200, json={"subscriber": {
            "entitlements": {"premium": {"product_identifier": "newzi_premium_monthly", "purchase_date": "2026-10-20T11:00:00Z", "expires_date": expires}},
            "subscriptions": {"newzi_premium_monthly": {"store": "app_store", "unsubscribe_detected_at": unsubscribed, "billing_issues_detected_at": None}}}})
    return httpx.Client(transport=httpx.MockTransport(answer))


def test_with_the_secret_key_the_plan_comes_from_revenuecat(setup, monkeypatch):
    from newzi_backend.revenuecat import handle_webhook, sync
    from newzi_backend.subscriptions import subscription_for
    repo, uid = setup
    monkeypatch.setenv("REVENUECAT_SECRET_KEY", "sk_teste")
    # The event says annual, RevenueCat says monthly: RevenueCat wins.
    assert handle_webhook(repo, "segredo", event(uid, "INITIAL_PURCHASE"), client=subscriber_client(), now=NOW) == (200, {"status": "active"})
    assert subscription_for(repo, uid, NOW)["period"] == "monthly"
    assert sync(repo, uid, subscriber_client(unsubscribed="2026-10-20T11:30:00Z"), NOW) == "canceled"
    assert sync(repo, uid, subscriber_client(expires="2026-10-20T11:59:00Z"), NOW) == "expired"
    assert handle_webhook(repo, "segredo", event(uid, "RENEWAL"), client=subscriber_client(fail=True), now=NOW)[0] == 503
    assert sync(repo, uid, subscriber_client(fail=True), NOW) is None


def test_sync_without_the_secret_key_changes_nothing(setup):
    from newzi_backend.revenuecat import sync
    repo, uid = setup
    assert sync(repo, uid, now=NOW) is None and row(repo, uid) is None
