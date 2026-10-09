import http.client
import os
from concurrent.futures import ThreadPoolExecutor

import pytest

import servers
from contract_scenario import Client


@pytest.fixture()
def api():
    with servers.running(os.getenv("TEST_DATABASE_URL")) as (base_url, _seed):
        yield Client(base_url)


def register(api, email):
    status, body, _ = api.request("POST", "/api/v1/auth/register", {"email": email, "password": "password123", "display_name": "X"})
    assert status == 201
    return body["session"]["token"], body["user"]["id"]


def test_per_user_routes_require_authentication(api):
    token, uid = register(api, "a@x.com")
    other, _ = register(api, "b@x.com")
    assert api.request("GET", f"/api/v1/users/{uid}/preferences")[0] == 401
    assert api.request("PUT", f"/api/v1/users/{uid}/preferences", {"briefing_size": 5})[0] == 401
    assert api.request("GET", f"/api/v1/users/{uid}/briefings")[0] == 401
    assert api.request("GET", f"/api/v1/users/{uid}/preferences", token=other)[0] == 403
    assert api.request("GET", f"/api/v1/users/{uid}/preferences", token=token)[0] == 200


def test_delete_device_returns_204_without_body(api):
    token, _ = register(api, "a@x.com")
    status, device, _ = api.request("POST", "/api/v1/me/devices", {"platform": "ANDROID", "push_token": "token-123456"}, token=token)
    assert status == 201
    status, body, _ = api.request("DELETE", f"/api/v1/me/devices/{device['id']}", token=token)
    assert status == 204 and body == b""


def test_logout_revokes_local_session(api):
    token, _ = register(api, "a@x.com")
    assert api.request("POST", "/api/v1/auth/logout", token=token)[0] == 200
    assert api.request("GET", "/api/v1/me", token=token)[0] == 401


def test_login_rate_limit_is_per_client_and_per_account(api):
    register(api, "a@x.com"); register(api, "b@x.com")
    codes = [api.request("POST", "/api/v1/auth/login", {"email": "a@x.com", "password": "bad-password"},
                         headers={"X-Real-IP": "10.0.0.1"})[0] for _ in range(11)]
    assert codes[0] == 401 and codes[-1] == 429
    # Another client and another account are unaffected.
    assert api.request("POST", "/api/v1/auth/login", {"email": "b@x.com", "password": "password123"},
                       headers={"X-Real-IP": "10.0.0.2"})[0] == 200
    # The targeted account stays limited from fresh addresses.
    assert api.request("POST", "/api/v1/auth/login", {"email": "a@x.com", "password": "bad-password"},
                       headers={"X-Real-IP": "10.9.9.9"})[0] == 429


def test_oversized_body_is_rejected(api):
    connection = http.client.HTTPConnection(api.host, api.port, timeout=30)
    connection.putrequest("PUT", "/api/v1/me/saved"); connection.putheader("Content-Length", str(5 * 1024 * 1024)); connection.endheaders()
    assert connection.getresponse().status == 413


def test_concurrent_requests_do_not_interfere(api):
    token, _ = register(api, "a@x.com")

    def hit(index):
        if index % 2:
            return api.request("PUT", "/api/v1/me/saved", {"story": {"id": f"s{index}", "headline": "x"}}, token=token)[0]
        return api.request("GET", "/api/v1/me/home", token=token)[0]
    with ThreadPoolExecutor(16) as pool:
        assert set(pool.map(hit, range(120))) == {200}
    assert len(api.request("GET", "/api/v1/me/saved", token=token)[1]["items"]) == 60
