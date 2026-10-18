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


def test_blocked_permission_keeps_the_phone_linked_but_silent(repo):
    from newzi_backend.notifications import NotificationService
    provider = RecordingProvider(); service = NotificationService(repo, provider=provider)
    device = service.register_device("u1", {"platform": "IOS", "push_token": "token-ios-0000001", "permission": "AUTHORIZED"})
    add_job(repo, "j1", "u1", device["id"])
    blocked = service.register_device("u1", {"platform": "IOS", "push_token": "token-ios-0000001", "permission": "DENIED"})
    assert blocked["id"] == device["id"] and not blocked["enabled"] and job_status(repo, "j1") == "CANCELLED"
    assert service.register_device("u1", {"platform": "IOS", "push_token": "token-ios-0000001", "permission": "PROVISIONAL"})["enabled"]


def test_new_token_on_the_same_phone_retires_the_old_one(repo):
    from newzi_backend.notifications import NotificationService
    service = NotificationService(repo, provider=RecordingProvider())
    old = service.register_device("u1", {"platform": "ANDROID", "push_token": "token-old-0000001", "device_identifier": "phone-1"})
    add_job(repo, "j1", "u1", old["id"])
    new = service.register_device("u1", {"platform": "ANDROID", "push_token": "token-new-0000001", "device_identifier": "phone-1"})
    enabled = dict(repo.db.execute("SELECT id,enabled FROM push_devices").fetchall())
    assert enabled == {old["id"]: 0, new["id"]: 1} and job_status(repo, "j1") == "CANCELLED"


def test_switch_turned_off_after_queueing_cancels_the_push(repo):
    from newzi_backend.notifications import NotificationService
    provider = RecordingProvider(); service = NotificationService(repo, provider=provider)
    device = service.register_device("u1", {"platform": "ANDROID", "push_token": "token-abcdef-123"})
    add_job(repo, "j1", "u1", device["id"])
    service.save_settings("u1", {"daily_briefing_enabled": False})
    assert service.run_once().get("cancelled") == 1 and job_status(repo, "j1") == "CANCELLED" and not provider.sent


def test_settings_show_briefing_time_and_breaking_rules_and_reject_bad_values(repo, monkeypatch):
    from newzi_backend.notifications import NotificationService
    monkeypatch.setenv("BREAKING_QUIET_HOURS", "23-6")
    service = NotificationService(repo, provider=RecordingProvider())
    settings = service.public_settings("u1")
    assert settings["briefing_time"] == "06:00" and settings["briefing_size"] == 10 and settings["active_devices"] == 0
    assert settings["breaking_news_rules"] == {"min_sources": 3, "quiet_hours": {"start": 23, "end": 6}}
    for bad in ({}, {"daily_briefing_enabled": "no"}, {"unknown": True}):
        with pytest.raises(ValueError):
            service.save_settings("u1", bad)


def test_daily_briefing_message_says_how_many_stories_and_minutes():
    from newzi_backend.notifications import daily_briefing_message, wants
    message = daily_briefing_message("d1", 10, 290_000)
    assert message["title"] == "Seu resumo de hoje está pronto" and message["body"] == "10 notícias selecionadas para você · 5 min"
    assert message["data"] == {"type": "DAILY_BRIEFING", "briefing_id": "d1", "delivery_id": "d1"}
    assert daily_briefing_message("d1")["body"] == "Seu resumo diário está pronto para começar o dia."
    assert wants({"notifications_enabled": True, "breaking_news_enabled": True}, "BREAKING_NEWS")
    assert not wants({"notifications_enabled": False, "breaking_news_enabled": True}, "BREAKING_NEWS")
    assert not wants({"notifications_enabled": True, "daily_briefing_enabled": True}, "UNKNOWN")


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


def test_users_with_the_same_preferences_never_share_an_edition(repo):
    """Briefings are per user: an edition composed for one user is never served to another (N09)."""
    from newzi_backend.scheduling import BriefingGenerationWorker, BriefingScheduler, FixtureBriefingGenerator
    scheduler = BriefingScheduler(repo)
    worker = BriefingGenerationWorker(repo, generator=FixtureBriefingGenerator())
    for uid in ("u1", "u2"):
        assert scheduler.schedule_user_now(uid)["scheduled"]
        worker.run_once()
    rows = repo.db.execute("SELECT d.user_id,d.edition_id,e.profile_key FROM user_briefing_deliveries d JOIN briefing_editions e ON e.id=d.edition_id").fetchall()
    assert len(rows) == 2 and rows[0]["edition_id"] != rows[1]["edition_id"]
    assert all(row["profile_key"].endswith("_user_" + row["user_id"]) for row in rows)


def test_following_everything_still_rebuilds_the_briefing_when_its_profile_changes():
    """N09: "Quero acompanhar tudo" has no topic list, but a new language or size is a new briefing."""
    from newzi_backend.product_backend import ProductService
    calls = []
    service = types.SimpleNamespace(scheduler=types.SimpleNamespace(regenerate_for_preferences=lambda uid: calls.append(uid) or {"scheduled": True}))
    everything = {"topics": [], "content_scope": "all", "language": "pt-BR", "briefing_size": 10, "country_scope": "BOTH", "briefing_time": "06:00", "timezone": "UTC"}
    assert ProductService.preferences_updated(service, "u1", everything, {**everything, "language": "en"})["scheduled"]
    assert calls == ["u1"]
    assert ProductService.preferences_updated(service, "u1", everything, dict(everything))["reason"] == "NO_PIPELINE_CHANGE"


def test_flipping_switches_while_testing_is_not_rate_limited(repo):
    """Opening the screen and flipping a switch on and off a dozen times in a minute must keep saving."""
    from newzi_backend.product_backend import ProductService
    service = ProductService(repo)
    service.notification_settings("u1")
    for index in range(20):
        assert service.notification_settings("u1", {"notifications_enabled": index % 2 == 1})["notifications_enabled"] == (index % 2 == 1)



def test_profile_photo_is_resized_served_by_a_random_name_and_removed_with_the_account(repo, tmp_path, monkeypatch):
    import base64, io
    from PIL import Image
    from newzi_backend import avatars
    monkeypatch.setenv("AVATAR_STORAGE_ROOT", str(tmp_path))
    buffer = io.BytesIO(); Image.new("RGB", (1200, 800), "red").save(buffer, "PNG")
    url = avatars.save_avatar(repo, "u1", base64.b64encode(buffer.getvalue()).decode())
    name = url.rsplit("/", 1)[1]
    with Image.open(avatars.avatar_path(name)) as stored:
        assert stored.format == "JPEG" and max(stored.size) == 512
    second = avatars.save_avatar(repo, "u1", base64.b64encode(buffer.getvalue()).decode())
    assert avatars.avatar_path(name) is None and avatars.photo_url(repo.get_user("u1")) == second
    assert avatars.avatar_path("../product_backend.sqlite3") is None
    for bad in ("not base64!", base64.b64encode(b"plain text").decode(), ""):
        with pytest.raises(ValueError):
            avatars.save_avatar(repo, "u1", bad)
    avatars.delete_avatar_file(repo.get_user("u1"))
    assert avatars.avatar_path(second.rsplit("/", 1)[1]) is None
