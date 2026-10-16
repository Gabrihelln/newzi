import types

import pytest


@pytest.fixture()
def repo(repo):
    from conftest import add_user
    add_user(repo, "u1"); add_user(repo, "u2")
    return repo


class RecordingProvider:
    name = "recording"
    def __init__(self): self.sent = []
    def send(self, token, title, body, data):
        from newzi_backend.notifications import PushResult
        self.sent.append(token); return PushResult(True, "message-1")


def add_job(repo, job_id, user_id, device_id):
    repo.db.execute("""INSERT INTO notification_jobs(id,user_id,delivery_id,device_id,notification_type,scheduled_for,status,
        attempt_count,max_attempts,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (job_id, user_id, "d_" + job_id, device_id, "DAILY_BRIEFING", "2000-01-01T00:00:00+00:00", "PENDING", 0, 3, "t", "t"))
    repo.db.commit()


def job_status(repo, job_id):
    return repo.db.execute("SELECT status FROM notification_jobs WHERE id=?", (job_id,)).fetchone()[0]


def test_disabled_device_never_receives_push(repo):
    from newzi_backend.notifications import NotificationService
    provider = RecordingProvider(); service = NotificationService(repo, provider=provider)
    device = service.register_device("u1", {"platform": "ANDROID", "push_token": "token-abcdef-123"})
    add_job(repo, "j1", "u1", device["id"]); service.disable_device("u1", device["id"])
    assert service.run_once().get("cancelled") == 1
    assert job_status(repo, "j1") == "CANCELLED" and not provider.sent


def test_logout_disables_only_the_signed_out_phone(repo):
    from newzi_backend.notifications import NotificationService
    from newzi_backend.product_backend import ProductService
    service = NotificationService(repo, provider=RecordingProvider())
    phone = service.register_device("u1", {"platform": "IOS", "push_token": "token-iphone-123"})
    other = service.register_device("u1", {"platform": "ANDROID", "push_token": "token-android-123"})
    backend = types.SimpleNamespace(repo=repo, identity=types.SimpleNamespace(revoke=lambda token: None))
    ProductService.logout(backend, "u1", "session", "token-iphone-123")
    enabled = dict(repo.db.execute("SELECT id,enabled FROM push_devices").fetchall())
    assert enabled == {phone["id"]: 0, other["id"]: 1}


def test_reassigned_device_drops_previous_owner_pushes(repo):
    from newzi_backend.notifications import NotificationService
    provider = RecordingProvider(); service = NotificationService(repo, provider=provider)
    device = service.register_device("u1", {"platform": "ANDROID", "push_token": "token-abcdef-123"})
    add_job(repo, "j1", "u1", device["id"])
    moved = service.register_device("u2", {"platform": "IOS", "push_token": "token-abcdef-123"})
    assert moved["id"] == device["id"]
    assert repo.db.execute("SELECT user_id FROM push_devices WHERE id=?", (device["id"],)).fetchone()[0] == "u2"
    assert job_status(repo, "j1") == "CANCELLED"
    add_job(repo, "j2", "u1", device["id"]); service.run_once()
    assert job_status(repo, "j2") == "CANCELLED" and not provider.sent


@pytest.fixture()
def fcm(monkeypatch):
    """FCMPushProvider wired to a stub of the Firebase Admin messaging API."""
    from firebase_admin import exceptions
    from newzi_backend.notifications import FCMPushProvider

    class Messaging:
        UnregisteredError = type("UnregisteredError", (exceptions.NotFoundError,), {})
        SenderIdMismatchError = type("SenderIdMismatchError", (exceptions.PermissionDeniedError,), {})
        QuotaExceededError = type("QuotaExceededError", (exceptions.ResourceExhaustedError,), {})
        Message = Notification = AndroidConfig = APNSConfig = APNSPayload = Aps = staticmethod(lambda *a, **k: None)
        channels = []
        AndroidNotification = staticmethod(lambda channel_id=None, **k: Messaging.channels.append(channel_id))
        error = None

        @classmethod
        def send(cls, message):
            if cls.error: raise cls.error
            return "projects/p/messages/1"
    provider = FCMPushProvider(); provider._messaging = Messaging
    return provider, Messaging


def firebase_error(cls, message="error"):
    return cls(message)


@pytest.mark.parametrize("make_error,expected", [
    (lambda m, e: firebase_error(m.UnregisteredError), ("TOKEN_INVALID", True, False)),
    (lambda m, e: firebase_error(e.InvalidArgumentError, "The registration token is not a valid FCM registration token"), ("TOKEN_INVALID", True, False)),
    (lambda m, e: firebase_error(e.InvalidArgumentError, "bad payload"), ("PROVIDER_REJECTED", False, False)),
    (lambda m, e: firebase_error(e.UnavailableError), ("PROVIDER_UNAVAILABLE", False, True)),
    (lambda m, e: firebase_error(m.QuotaExceededError), ("PROVIDER_UNAVAILABLE", False, True)),
    (lambda m, e: type("DefaultCredentialsError", (Exception,), {})(), ("FCM_NOT_CONFIGURED", False, False)),
    (lambda m, e: ConnectionError(), ("PROVIDER_UNAVAILABLE", False, True)),
])
def test_fcm_errors_are_classified(fcm, make_error, expected):
    from firebase_admin import exceptions
    provider, messaging = fcm
    messaging.error = make_error(messaging, exceptions)
    result = provider.send("token", "title", "body", {"x": 1})
    assert (result.failure_reason, result.token_invalid, result.retryable) == expected


def test_fcm_success(fcm):
    provider, messaging = fcm
    result = provider.send("token", "title", "body", {"x": 1})
    assert result.success and result.provider_message_id == "projects/p/messages/1"
    provider.send("token", "title", "body", {"type": "BREAKING_NEWS"})
    assert messaging.channels == ["daily_briefing", "breaking_news"]     # each kind on its own Android channel


def test_rate_limiter_prunes_idle_keys(monkeypatch):
    from newzi_backend import identity
    clock = types.SimpleNamespace(now=0.0)
    monkeypatch.setattr(identity.time, "monotonic", lambda: clock.now)
    limiter = identity.LocalAuthRateLimiter(limit=2, window_seconds=60)
    assert limiter.allow("a") and limiter.allow("a") and not limiter.allow("a")
    clock.now = 61
    assert limiter.allow("b") and "a" not in limiter.hits


def test_new_briefing_time_starts_tomorrow_once_todays_briefing_is_made(repo):
    from datetime import datetime, timezone
    from newzi_backend.product_backend import ProductService
    from newzi_backend.scheduling import FixedClock
    service = ProductService(repo, clock=FixedClock(datetime(2026, 10, 16, 15, 0, tzinfo=timezone.utc)))
    repo.save_preferences("u1", {"timezone": "UTC"}); repo.save_preferences("u2", {"timezone": "UTC"})
    repo.db.execute("""INSERT INTO user_briefing_deliveries(id,user_id,edition_id,local_date,delivery_time,timezone,status,created_at)
        VALUES(?,?,?,?,?,?,?,?)""", ("d_u1", "u1", "e1", "2026-10-16", "06:00", "UTC", "READY", "t"))
    saved = {user_id: service.save_preferences(user_id, {"briefing_time": "21:25"}) for user_id in ("u1", "u2")}
    # Today's briefing keeps its time: the new one would only re-announce old news.
    assert repo.db.execute("SELECT delivery_time FROM user_briefing_deliveries WHERE id='d_u1'").fetchone()[0] == "06:00"
    assert saved["u1"]["next_briefing"] == {"date": "2026-10-17", "time": "21:25", "day": "TOMORROW"}
    # Without a briefing made today, the new time still applies today.
    assert saved["u2"]["next_briefing"] == {"date": "2026-10-16", "time": "21:25", "day": "TODAY"}
    assert service.preferences("u1")["next_briefing"]["day"] == "TOMORROW"
