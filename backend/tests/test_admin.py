"""Analytics Newzi (painel.newzi.app): the panel's sign-in, daily activity and the read-only screens."""
import os
from datetime import datetime, timedelta, timezone

import pytest

import servers
from conftest import add_user
from contract_scenario import Client

PASSWORD = "senha-do-painel-123"
SCREENS = ("overview", "users", "retention", "briefings", "content", "notifications", "subscriptions", "football", "system")


@pytest.fixture()
def panel(monkeypatch):
    from newzi_backend import admin
    monkeypatch.setenv("ADMIN_EMAIL", "Dono@Newzi.app")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", admin.hash_password(PASSWORD))
    monkeypatch.delenv("ADMIN_HOST", raising=False)
    admin._seen.update(day=None, users=set())


@pytest.fixture()
def api(panel):
    with servers.running(os.getenv("TEST_DATABASE_URL")) as (base_url, _seed):
        yield Client(base_url)


def sign_in(api, password=PASSWORD, email="dono@newzi.app"):
    status, body, response = api.request("POST", "/api/v1/admin/login", {"email": email, "password": password})
    return status, body, response.getheader("Set-Cookie") or ""


def cookie_of(set_cookie):
    return {"Cookie": set_cookie.split(";")[0]}


def test_panel_routes_are_hidden_until_configured(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    with servers.running(os.getenv("TEST_DATABASE_URL")) as (base_url, _seed):
        api = Client(base_url)
        assert api.request("POST", "/api/v1/admin/login", {"email": "a@x.com", "password": "x"})[0] == 404
        assert api.request("GET", "/api/v1/admin/overview")[0] == 404


def test_sign_in_opens_a_cookie_session_for_every_screen(api):
    for screen in SCREENS:
        assert api.request("GET", f"/api/v1/admin/{screen}")[0] == 401
    assert sign_in(api, "errada")[0] == 401
    assert sign_in(api, PASSWORD, "outro@newzi.app")[0] == 401
    status, body, set_cookie = sign_in(api)
    assert status == 200 and body["email"] == "dono@newzi.app"
    flags = set_cookie.lower()
    assert "httponly" in flags and "secure" in flags and "samesite=strict" in flags and "path=/api/v1/admin" in flags
    headers = cookie_of(set_cookie)
    for screen in SCREENS:
        status, body, _ = api.request("GET", f"/api/v1/admin/{screen}", headers=headers)
        assert status == 200, (screen, body)
    assert api.request("GET", "/api/v1/admin/session", headers=headers)[0] == 200
    assert api.request("POST", "/api/v1/admin/logout", headers=headers)[0] == 200
    assert api.request("GET", "/api/v1/admin/overview", headers=headers)[0] == 401


def test_panel_answers_only_on_its_host(api, monkeypatch):
    monkeypatch.setenv("ADMIN_HOST", "painel.newzi.app")
    assert sign_in(api)[0] == 404
    status, _, _ = api.request("POST", "/api/v1/admin/login", {"email": "dono@newzi.app", "password": PASSWORD},
                               headers={"Host": "painel.newzi.app"})
    assert status == 200


def test_app_requests_count_the_user_once_a_day_and_show_in_the_panel(api):
    status, body, _ = api.request("POST", "/api/v1/auth/register", {"email": "leitor@x.com", "password": "password123", "display_name": "L"})
    token, uid = body["session"]["token"], body["user"]["id"]
    for _ in range(3):
        assert api.request("GET", "/api/v1/me", token=token)[0] == 200
    headers = cookie_of(sign_in(api)[2])
    overview = api.request("GET", "/api/v1/admin/overview", headers=headers)[1]
    assert overview["dau"] == 1 and overview["users_total"] >= 1
    listed = api.request("GET", "/api/v1/admin/users?query=leitor", headers=headers)[1]
    assert listed["total"] == 1 and listed["users"][0]["id"] == uid and listed["users"][0]["active_days"] == 1
    detail = api.request("GET", f"/api/v1/admin/users/{uid}", headers=headers)[1]
    assert detail["user"]["email"] == "leitor@x.com" and len(detail["activity"]) == 1 and "password_hash" not in detail["user"]
    assert api.request("GET", "/api/v1/admin/users/nobody", headers=headers)[0] == 404


def test_five_wrong_passwords_lock_the_sign_in(repo, panel):
    from newzi_backend import admin
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    for _ in range(admin.MAX_FAILURES):
        with pytest.raises(PermissionError):
            admin.login(repo, "dono@newzi.app", "errada", now=now)
    with pytest.raises(LookupError):
        admin.login(repo, "dono@newzi.app", PASSWORD, now=now)
    later = now + timedelta(minutes=admin.LOCK_MINUTES + 1)
    assert admin.session_valid(repo, admin.login(repo, "dono@newzi.app", PASSWORD, now=later), now=later)
    failed = repo.db.execute("SELECT COUNT(*) FROM admin_actions WHERE action='login' AND ok=0").fetchone()[0]
    assert failed == admin.MAX_FAILURES


def test_a_new_password_ends_open_sessions_and_sessions_expire(repo, panel, monkeypatch):
    from newzi_backend import admin
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    token = admin.login(repo, "dono@newzi.app", PASSWORD, now=now)
    assert admin.session_valid(repo, token, now=now)
    assert not admin.session_valid(repo, token, now=now + timedelta(hours=admin.SESSION_HOURS, seconds=1))
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", admin.hash_password("outra-senha-123"))
    assert not admin.session_valid(repo, token, now=now)


def test_password_hash_never_holds_the_password_or_a_dollar_sign():
    from newzi_backend.admin import hash_password, verify_password
    stored = hash_password(PASSWORD)
    assert PASSWORD not in stored and "$" not in stored and stored != hash_password(PASSWORD)
    assert verify_password(PASSWORD, stored) and not verify_password("errada", stored) and not verify_password(PASSWORD, "lixo")


def test_screens_count_by_the_owners_local_day(repo, panel):
    from newzi_backend import admin, admin_metrics
    from newzi_backend.subscriptions import grant_manual
    add_user(repo, "leitor"); add_user(repo, "pagante")
    # 01:30 UTC on the 28th is still the 27th in São Paulo.
    late = datetime(2026, 10, 28, 1, 30, tzinfo=timezone.utc)
    admin.record_activity(repo, "leitor", now=late)
    admin.record_activity(repo, "leitor", now=late + timedelta(minutes=5))
    assert repo.db.execute("SELECT day FROM user_activity_days").fetchall()[0][0] == "2026-10-27"
    grant_manual(repo, "pagante")
    overview = admin_metrics.overview(repo, days=7, now=late)
    assert overview["dau"] == 1 and overview["plans"] == {"premium": 1, "paid": 0, "manual": 1, "monthly": 0, "annual": 0}
    assert overview["series"]["active"][-1] == {"day": "2026-10-27", "value": 1}
    plans = {row["id"]: row["plan"] for row in admin_metrics.users(repo, now=late)["users"]}
    assert plans == {"leitor": "basic", "pagante": "premium_manual"}
    assert admin_metrics.users(repo, plan="premium_manual", now=late)["total"] == 1
    content = admin_metrics.content(repo, days=7, now=late, health={"sources": [{"id": "a", "status": "BROKEN"}, {"id": "b", "status": "OK"}]})
    assert content["sources"]["by_status"] == {"BROKEN": 1, "OK": 1} and [row["id"] for row in content["sources"]["attention"]] == ["a"]
    assert content["topics_followed"][0]["users"] == 2


def test_deleting_an_account_removes_its_activity(repo, panel):
    from newzi_backend import admin
    add_user(repo, "leitor")
    admin.record_activity(repo, "leitor")
    repo.delete_user("leitor")
    assert repo.db.execute("SELECT COUNT(*) FROM user_activity_days").fetchone()[0] == 0
