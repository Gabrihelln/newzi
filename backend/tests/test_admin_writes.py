"""Analytics Newzi, etapas 2 and 3: Premium given from the panel, pushes from the panel, and the sales numbers."""
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

import servers
from conftest import add_user
from contract_scenario import Client

PASSWORD = "senha-do-painel-123"
NOW = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)      # 12:00 in São Paulo


@pytest.fixture()
def panel(monkeypatch):
    from newzi_backend import admin
    monkeypatch.setenv("ADMIN_EMAIL", "dono@newzi.app")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", admin.hash_password(PASSWORD))
    monkeypatch.delenv("ADMIN_HOST", raising=False)
    monkeypatch.delenv("REVENUECAT_API_V2_KEY", raising=False)


def add_device(repo, uid, platform="ANDROID", token=None):
    repo.db.execute("""INSERT INTO push_devices(id,user_id,platform,push_token,timezone,created_at,updated_at,last_seen_at)
        VALUES(?,?,?,?,?,?,?,?)""", ("device_" + uid + platform, uid, platform, token or "token-" + uid + platform, "UTC", "t", "t", "t"))
    repo.db.commit()


# ------------------------------------------------------------- Premium from the panel
def test_courtesy_runs_from_the_first_to_the_end_of_the_last_day(repo, panel):
    from newzi_backend import admin_premium
    from newzi_backend.subscriptions import is_premium, subscription_for
    add_user(repo, "leitor")
    result = admin_premium.give(repo, {"emails": "LEITOR@x", "start_day": "2026-11-01", "end_day": "2026-11-30", "reason": "parceria"},
                                "dono@newzi.app", NOW)
    assert [item["user_id"] for item in result["given"]] == ["leitor"] and result["missing"] == []
    # 01/11 00:00 to 30/11 23:59:59 in São Paulo.
    assert result["starts_at"] == "2026-11-01T03:00:00.000Z" and result["ends_at"] == "2026-12-01T03:00:00.000Z"
    assert not is_premium(repo, "leitor", NOW)                          # scheduled
    assert admin_premium.grants(repo, now=NOW)["grants"][0]["status"] == "agendado"
    during = datetime(2026, 11, 30, 23, 0, tzinfo=timezone.utc)
    plan = subscription_for(repo, "leitor", during)
    assert plan["tier"] == "premium" and plan["source"] == "courtesy" and plan["expires_at"] == "2026-12-01T03:00:00.000Z"
    assert not plan["will_renew"] and plan["period"] is None
    assert not is_premium(repo, "leitor", datetime(2026, 12, 1, 3, 0, tzinfo=timezone.utc))


def test_courtesy_and_store_plan_never_overwrite_each_other(repo, panel):
    from newzi_backend import admin_premium, revenuecat
    from newzi_backend.subscriptions import is_premium, subscription_for
    add_user(repo, "leitor")
    grant_id = admin_premium.give(repo, {"emails": ["leitor@x"], "start_day": "2026-10-27", "end_day": "2027-01-31"}, None, NOW)["given"][0]["grant_id"]
    # The reader then buys in the store, and the subscription later expires: the courtesy is still there.
    revenuecat.write(repo, "leitor", product_id="newzi_monthly", store="app_store", started_at="2026-10-27T15:00:00.000Z",
                     expires_at="2026-11-27T15:00:00.000Z", billing_issue=False, unsubscribed=False, now=NOW)
    assert subscription_for(repo, "leitor", NOW)["source"] == "store"
    later = datetime(2026, 12, 15, tzinfo=timezone.utc)
    assert subscription_for(repo, "leitor", later)["source"] == "courtesy"
    # Ending the courtesy leaves a store plan alone.
    admin_premium.end(repo, grant_id, "dono@newzi.app", NOW)
    assert is_premium(repo, "leitor", NOW) and not is_premium(repo, "leitor", later)
    assert admin_premium.grants(repo, "leitor", NOW)["grants"][0]["status"] == "retirado"
    with pytest.raises(LookupError):
        admin_premium.end(repo, grant_id, None, NOW)


def test_giving_premium_validates_and_reports_unknown_emails(repo, panel):
    from newzi_backend import admin_premium
    add_user(repo, "leitor")
    with pytest.raises(ValueError):
        admin_premium.give(repo, {"emails": "leitor@x", "start_day": "2026-11-10", "end_day": "2026-11-01"}, None, NOW)
    with pytest.raises(ValueError):
        admin_premium.give(repo, {"emails": "leitor@x", "start_day": "2026-10-01", "end_day": "2026-10-20"}, None, NOW)
    with pytest.raises(ValueError):
        admin_premium.give(repo, {"emails": "leitor@x", "start_day": "2026-11-01", "end_day": "2026-11-02", "reason": "x"}, None, NOW)
    result = admin_premium.give(repo, {"emails": "leitor@x; ninguem@x", "start_day": "2026-10-27", "end_day": "2026-10-27"}, None, NOW)
    assert len(result["given"]) == 1 and result["missing"] == ["ninguem@x"]
    grant_id = result["given"][0]["grant_id"]
    changed = admin_premium.change(repo, grant_id, {"start_day": "2026-10-27", "end_day": "2026-12-31", "reason": "suporte"}, NOW)
    assert changed["ends_at"] == "2027-01-01T03:00:00.000Z" and changed["reason"] == "suporte"


def test_store_manual_rows_move_to_premium_grants(tmp_path):
    from newzi_backend import db as database
    from newzi_backend.migrations import MIGRATIONS, migrate
    connection = database.connect("sqlite:///" + (tmp_path / "old.sqlite3").as_posix())
    migrate(connection, [step for step in MIGRATIONS if step[0] < "0014"])
    connection.execute("""INSERT INTO users(id,email,display_name,language,timezone,created_at,updated_at,status)
        VALUES('u','u@x','u','pt-BR','UTC','t','t','ACTIVE')""")
    connection.execute("""INSERT INTO subscriptions(user_id,period,status,store,started_at,expires_at,auto_renew,updated_at)
        VALUES('u','monthly','active','manual','2026-10-01T00:00:00.000Z','2026-12-01T00:00:00.000Z',0,'2026-10-01T00:00:00.000Z')""")
    connection.commit()
    assert migrate(connection) == ["0014_panel_writes"]
    assert connection.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0] == 0
    row = connection.execute("SELECT user_id,starts_at,ends_at,reason FROM premium_grants").fetchone()
    assert tuple(row) == ("u", "2026-10-01T00:00:00.000Z", "2026-12-01T00:00:00.000Z", "teste")


# ------------------------------------------------------------- pushes from the panel
def test_audiences_pick_the_right_people_and_phones(repo, panel):
    from newzi_backend import admin_push
    from newzi_backend.admin import record_activity, _seen
    from newzi_backend.subscriptions import add_grant
    for uid in ("free", "paid", "former", "gift", "quiet"):
        add_user(repo, uid, topics=("SPORTS",) if uid == "free" else ("TECHNOLOGY",))
        add_device(repo, uid)
    add_device(repo, "paid", "IOS")
    repo.db.execute("""INSERT INTO subscriptions(user_id,period,status,store,started_at,expires_at,auto_renew,updated_at) VALUES
        ('paid','monthly','active','app_store','2026-10-01T00:00:00.000Z','2026-11-20T00:00:00.000Z',1,'t'),
        ('former','monthly','expired','app_store','2026-08-01T00:00:00.000Z','2026-09-01T00:00:00.000Z',0,'t')""")
    repo.db.execute("INSERT INTO notification_settings(user_id,notifications_enabled,updated_at) VALUES('quiet',0,'t')")
    repo.db.commit()
    add_grant(repo, "gift", "2026-10-01T00:00:00.000Z", "2026-12-01T00:00:00.000Z")
    _seen.update(day=None, users=set())
    record_activity(repo, "free", now=NOW)
    users = lambda **audience: admin_push.resolve_users(repo, admin_push._audience(audience), NOW)
    assert users() == {"free", "paid", "former", "gift", "quiet"}
    assert users(segment="premium_now") == {"paid", "gift"}
    assert users(segment="ex_premium") == {"former"}
    assert users(segment="never_premium") == {"free", "quiet"}
    assert users(segment="not_premium") == {"free", "former", "quiet"}
    assert users(topic="SPORTS") == {"free"}
    assert users(inactive_days=7) == {"paid", "former", "gift", "quiet"}
    assert users(emails="PAID@x, gift@x") == {"paid", "gift"}
    preview = admin_push.preview(repo, {"audience": {"segment": "premium_now"}}, NOW)
    assert preview == {"users": 2, "users_reachable": 2, "devices": 3, "by_platform": {"ANDROID": 2, "IOS": 1}, "without_device": 0}
    # Whoever turned every notification off in the app is not reached.
    assert admin_push.preview(repo, {"audience": {"emails": "quiet@x"}}, NOW)["devices"] == 0
    assert admin_push.preview(repo, {"audience": {"platform": "IOS"}}, NOW)["devices"] == 1


def test_a_campaign_sent_now_reaches_every_phone_once_with_its_destination(repo, panel):
    from newzi_backend import admin_push
    from newzi_backend.notifications import DevelopmentPushProvider, NotificationService
    add_user(repo, "a"); add_user(repo, "b")
    add_device(repo, "a"); add_device(repo, "b", "IOS")
    campaign = admin_push.create(repo, {"kind": "promotion", "title": "Premium com 30% off", "body": "Só até domingo.",
                                        "target": {"screen": "Subscription"}, "audience": {}}, NOW)
    assert campaign["status"] == "SENDING" and campaign["users"] == 2 and campaign["devices"] == 2
    provider = DevelopmentPushProvider()
    service = NotificationService(repo, provider=provider)
    assert service.run_batch(now=NOW)["notifications_sent"] == 2
    sent = provider.sent[0]
    assert sent["title"] == "Premium com 30% off" and sent["data"]["type"] == "PROMOTION" and sent["data"]["screen"] == "Subscription"
    assert admin_push.get(repo, campaign["id"], NOW)["status"] == "SENT"
    assert admin_push.get(repo, campaign["id"], NOW)["results"] == {"sent": 2, "failed": 0, "cancelled": 0, "pending": 0}
    assert not admin_push.dispatch(repo, campaign["id"], NOW)          # never queued twice
    assert service.run_batch(now=NOW)["jobs_claimed"] == 0


def test_a_scheduled_campaign_waits_can_change_and_be_cancelled(repo, panel):
    from newzi_backend import admin_push
    add_user(repo, "a"); add_device(repo, "a")
    later = (NOW + timedelta(hours=3)).isoformat()
    campaign = admin_push.create(repo, {"kind": "announcement", "title": "Novidade", "body": "Chegou o resumo na hora.",
                                        "target": {"url": "https://newzi.app"}, "scheduled_for": later}, NOW)
    assert campaign["status"] == "SCHEDULED" and admin_push.dispatch_due(repo, NOW) == {"campaigns_dispatched": 0}
    updated = admin_push.update(repo, campaign["id"], {"kind": "announcement", "title": "Novidade!", "body": "Texto novo.",
                                                       "scheduled_for": later}, NOW)
    assert updated["title"] == "Novidade!"
    assert admin_push.dispatch_due(repo, NOW + timedelta(hours=3, minutes=1)) == {"campaigns_dispatched": 1}
    with pytest.raises(LookupError):
        admin_push.cancel(repo, campaign["id"], NOW)
    other = admin_push.create(repo, {"kind": "announcement", "title": "T", "body": "B", "scheduled_for": later}, NOW)
    assert admin_push.cancel(repo, other["id"], NOW)["status"] == "CANCELLED"
    assert repo.db.execute("SELECT COUNT(*) FROM notification_jobs WHERE delivery_id=?", (other["id"],)).fetchone()[0] == 0


def test_campaigns_reject_bad_input(repo, panel):
    from newzi_backend import admin_push
    base = {"kind": "announcement", "title": "T", "body": "B"}
    for bad in ({**base, "kind": "spam"}, {**base, "title": ""}, {**base, "title": "x" * 70},
                {**base, "target": {"url": "http://x"}}, {**base, "target": {"screen": "Admin"}},
                {**base, "audience": {"segment": "vip"}}, {**base, "scheduled_for": "2026-10-01T10:00:00-03:00"},
                {**base, "scheduled_for": "2026-11-01T10:00:00"}):
        with pytest.raises(ValueError):
            admin_push.create(repo, bad, NOW)


# ------------------------------------------------------------- sales (RevenueCat events)
def event(event_id, kind, at, **fields):
    return {"id": event_id, "type": kind, "event_timestamp_ms": int(at.timestamp() * 1000), "environment": "PRODUCTION", **fields}


def test_sales_numbers_come_from_the_webhook_events(repo, panel, monkeypatch):
    from newzi_backend import billing, revenuecat
    monkeypatch.setenv("REVENUECAT_WEBHOOK_AUTH", "segredo")
    monkeypatch.delenv("REVENUECAT_SECRET_KEY", raising=False)
    add_user(repo, "leitor")
    day = NOW - timedelta(days=2)
    events = [
        event("e1", "INITIAL_PURCHASE", day, app_user_id="leitor", period_type="TRIAL", price=0, price_in_purchased_currency=0, currency="BRL"),
        event("e2", "RENEWAL", day + timedelta(hours=1), app_user_id="leitor", period_type="NORMAL", is_trial_conversion=True,
              price=2.9, price_in_purchased_currency=14.9, currency="BRL", takehome_percentage=0.85),
        event("e3", "INITIAL_PURCHASE", day, app_user_id="ninguem", period_type="NORMAL", price=24, price_in_purchased_currency=119.9, currency="BRL"),
        event("e4", "CANCELLATION", day + timedelta(hours=2), app_user_id="ninguem", period_type="NORMAL", cancel_reason="CUSTOMER_SUPPORT",
              price=-24, price_in_purchased_currency=-119.9, currency="BRL"),
        event("e5", "CANCELLATION", day + timedelta(hours=3), app_user_id="leitor", period_type="NORMAL", cancel_reason="UNSUBSCRIBE"),
        event("e6", "INITIAL_PURCHASE", day, app_user_id="leitor", period_type="NORMAL", price=2.9, environment="SANDBOX"),
    ]
    for item in events + events[:1]:                                    # a redelivery counts once
        assert revenuecat.handle_webhook(repo, "segredo", {"event": item}, now=NOW)[0] == 200
    sales = billing.sales(repo, days=7, now=NOW)
    assert sales["totals"] == {"trial_started": 1, "trial_converted": 1, "new_paid": 1, "refund": 1, "cancellation": 1}
    assert sales["revenue"] == {"BRL": 14.9} and abs(sales["net_estimate"]["BRL"] - 14.9 * 0.85) < 0.01
    assert sales["trial_conversion"] == {"started": 1, "converted": 1, "cancelled": 0}
    assert sales["overview"] == {"configured": False}
    assert billing.sales(repo, days=7, include_sandbox=True, now=NOW)["totals"]["new_paid"] == 2
    # Deleting the account keeps the sale and drops the person.
    repo.delete_user("leitor")
    assert repo.db.execute("SELECT COUNT(*) FROM billing_events WHERE user_id IS NULL AND id='e2'").fetchone()[0] == 1


def test_revenuecat_overview_is_read_and_cached(monkeypatch):
    import httpx
    from newzi_backend import billing
    monkeypatch.setenv("REVENUECAT_API_V2_KEY", "sk_v2"); monkeypatch.setenv("REVENUECAT_PROJECT_ID", "proj1")
    calls = []

    def handler(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer sk_v2" and request.url.path == "/v2/projects/proj1/metrics/overview"
        return httpx.Response(200, json={"metrics": [{"id": "mrr", "name": "MRR", "unit": "$", "value": 149.0, "extra": 1}]})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    first = billing.overview(client, force=True)
    assert first["metrics"] == [{"id": "mrr", "name": "MRR", "description": None, "unit": "$", "period": None, "value": 149.0, "last_updated_at": None}]
    assert billing.overview(client) == first and len(calls) == 1
    failing = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(403)))
    assert billing.overview(failing, force=True) == {"configured": True, "error": "RevenueCat respondeu 403"}


# ------------------------------------------------------------- through the API
@pytest.fixture()
def api(panel):
    with servers.running(os.getenv("TEST_DATABASE_URL")) as (base_url, _seed):
        yield Client(base_url)


def test_changes_need_session_panel_header_and_confirmation(api):
    status, body, _ = api.request("POST", "/api/v1/auth/register", {"email": "leitor@x.com", "password": "password123", "display_name": "L"})
    uid = body["user"]["id"]
    cookie = api.request("POST", "/api/v1/admin/login", {"email": "dono@newzi.app", "password": PASSWORD})[2].getheader("Set-Cookie").split(";")[0]
    session = {"Cookie": cookie}
    write = {**session, "X-Newzi-Panel": "1"}
    give = {"emails": "leitor@x.com", "start_day": "2026-01-01", "end_day": "2099-12-31", "reason": "cortesia"}
    assert api.request("POST", "/api/v1/admin/premium-grants", give)[0] == 401
    assert api.request("POST", "/api/v1/admin/premium-grants", give, headers=session)[0] == 403
    status, result, _ = api.request("POST", "/api/v1/admin/premium-grants", give, headers=write)
    assert status == 200 and result["given"][0]["user_id"] == uid
    detail = api.request("GET", f"/api/v1/admin/users/{uid}", headers=session)[1]
    assert detail["plan"]["source"] == "courtesy" and detail["grants"][0]["status"] == "ativo"
    grant_id = result["given"][0]["grant_id"]
    assert api.request("POST", f"/api/v1/admin/premium-grants/{grant_id}/revoke", headers=write)[0] == 200
    assert api.request("POST", f"/api/v1/admin/premium-grants/{grant_id}/revoke", headers=write)[0] == 409

    push = {"kind": "announcement", "title": "Olá", "body": "Novidade no Newzi", "audience": {"emails": "leitor@x.com"}}
    assert api.request("POST", "/api/v1/admin/push", push, headers=write)[0] == 400                 # no ENVIAR
    status, preview, _ = api.request("POST", "/api/v1/admin/push/preview", push, headers=write)
    assert status == 200 and preview["users"] == 1
    status, campaign, _ = api.request("POST", "/api/v1/admin/push", {**push, "confirm": "enviar"}, headers=write)
    assert status == 200 and campaign["status"] in ("SENDING", "SENT")
    listed = api.request("GET", "/api/v1/admin/push", headers=session)[1]
    assert listed["campaigns"][0]["id"] == campaign["id"] and "Subscription" in listed["screens"]
    actions = [row["action"] for row in api.request("GET", "/api/v1/admin/actions", headers=session)[1]]
    assert actions == ["push_create", "premium_revoke", "premium_give"]
    assert json.loads(api.request("GET", "/api/v1/admin/actions", headers=session)[1][2]["detail_json"])["emails"] == "leitor@x.com"
    status, subscriptions, _ = api.request("GET", "/api/v1/admin/subscriptions", headers=session)
    assert status == 200 and "sales" in subscriptions
