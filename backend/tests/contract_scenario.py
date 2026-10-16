"""End-to-end API contract scenario.

The same request sequence runs against any server implementation; responses are normalized
and compared with tests/golden/contract.json, so a framework or database change that alters
a status code or a response body fails loudly.

Regenerate the golden file only for an intended contract change:
    python backend/tests/contract_scenario.py --write
"""
import http.client
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

GOLDEN = Path(__file__).with_name("golden") / "contract.json"


class Client:
    def __init__(self, base_url):
        parts = urlsplit(base_url); self.host = parts.hostname; self.port = parts.port

    def request(self, method, path, body=None, token=None, headers=None, raw_body=None):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=60)
        sent = dict(headers or {})
        if token: sent["Authorization"] = "Bearer " + token
        data = raw_body if raw_body is not None else (json.dumps(body).encode() if body is not None else None)
        if data is not None and "Content-Type" not in sent: sent["Content-Type"] = "application/json"
        connection.request(method, path, body=data, headers=sent)
        response = connection.getresponse(); payload = response.read(); connection.close()
        content_type = (response.getheader("Content-Type") or "").split(";")[0]
        if content_type == "application/json" and payload:
            return response.status, json.loads(payload), response
        return response.status, payload, response


def run(base_url, seed):
    """Execute the scenario; ``seed(topics)`` indexes deterministic content in the server's database."""
    from support import Normalizer
    client = Client(base_url); normalize = Normalizer(); records = []

    def call(step, method, path, body=None, token=None, **kwargs):
        status, payload, response = client.request(method, path, body, token, **kwargs)
        if isinstance(payload, bytes):
            content_type = (response.getheader("Content-Type") or "").split(";")[0]
            shown = {"content_type": content_type, "non_empty": bool(payload)} if payload else None
        else:
            shown = payload
        if step == "health" and isinstance(shown, dict):
            shown = {**shown, "database": "<dialect>"}  # the same contract holds for SQLite and PostgreSQL
        records.append({"step": step, "request": f"{method} {normalize.text(path)}", "status": status, "body": normalize(shown)})
        return status, payload

    # Public
    call("health", "GET", "/health")
    call("ready", "GET", "/ready")
    _, topics = call("topics", "GET", "/api/v1/topics")
    call("client config", "GET", "/api/v1/client/config")
    call("unknown route", "GET", "/api/v1/nope")

    # Local identity
    call("register invalid", "POST", "/api/v1/auth/register", {"email": "nope", "password": "password123", "display_name": "X"})
    call("register short password", "POST", "/api/v1/auth/register", {"email": "short@x.com", "password": "123", "display_name": "X"})
    _, a = call("register A", "POST", "/api/v1/auth/register", {"email": "ana@example.com", "password": "password123", "display_name": "Ana"})
    _, b = call("register B", "POST", "/api/v1/auth/register", {"email": "bia@example.com", "password": "password123", "display_name": "Bia"})
    call("register duplicate", "POST", "/api/v1/auth/register", {"email": "ANA@example.com", "password": "password123", "display_name": "Ana"})
    call("login wrong password", "POST", "/api/v1/auth/login", {"email": "ana@example.com", "password": "wrong-password"})
    call("login", "POST", "/api/v1/auth/login", {"email": "ana@example.com", "password": "password123"})
    ta, tb = a["session"]["token"], b["session"]["token"]; ua = a["user"]["id"]
    call("me without token", "GET", "/api/v1/me")
    call("me invalid scheme", "GET", "/api/v1/me", headers={"Authorization": "Basic abc"})
    call("me unknown token", "GET", "/api/v1/me", token="not-a-real-token")
    call("me", "GET", "/api/v1/me", token=ta)
    call("invalid json", "PUT", "/api/v1/me/preferences", token=ta, raw_body=b"{not json")

    # Preferences and onboarding
    call("preferences default", "GET", "/api/v1/me/preferences", token=ta)
    call("preferences invalid size", "PUT", "/api/v1/me/preferences", {"briefing_size": 7}, token=ta)
    call("preferences invalid topic", "PUT", "/api/v1/me/preferences", {"topics": ["NOT_A_TOPIC"]}, token=ta)
    call("preferences invalid timezone", "PUT", "/api/v1/me/preferences", {"timezone": "Mars/Base"}, token=ta)
    call("onboarding status", "GET", "/api/v1/me/onboarding", token=ta)
    seed(["TECHNOLOGY", "ECONOMY"])
    call("onboarding complete", "PUT", "/api/v1/me/onboarding",
         {"topics": ["TECHNOLOGY", "ECONOMY"], "briefing_time": "07:00", "briefing_size": 5, "audio_voice_id": "newzi_lucas"}, token=ta)
    call("today before generation", "GET", "/api/v1/me/briefings/today", token=ta)

    # Generation pipeline (fixture content, fake TTS)
    call("dev worker run", "POST", "/api/v1/dev/worker/run", token=ta)
    call("today content ready", "GET", "/api/v1/me/briefings/today", token=ta)
    call("dev audio run", "POST", "/api/v1/dev/audio/run", token=ta)
    _, today = call("today ready", "GET", "/api/v1/me/briefings/today", token=ta)
    delivery = today.get("id")
    call("home", "GET", "/api/v1/me/home", token=ta)
    call("history", "GET", "/api/v1/me/briefings?limit=5", token=ta)
    call("history page 2", "GET", "/api/v1/me/briefings?limit=1&cursor=1", token=ta)
    call("briefing by id", "GET", f"/api/v1/me/briefings/{delivery}", token=ta)
    call("briefing other user", "GET", f"/api/v1/me/briefings/{delivery}", token=tb)
    call("briefing missing", "GET", "/api/v1/me/briefings/delivery_doesnotexist", token=ta)
    _, audio = call("briefing audio", "GET", f"/api/v1/me/briefings/{delivery}/audio", token=ta)
    if isinstance(audio, dict) and audio.get("audio_url"):
        call("audio file", "GET", audio["audio_url"], token=ta)
        call("audio file stale version", "GET", audio["audio_url"].replace("v=", "v=stale"), token=ta)
        call("audio file without auth", "GET", audio["audio_url"])
    call("listening progress", "PUT", f"/api/v1/me/briefings/{delivery}/progress", {"progress_seconds": 1, "duration_seconds": 3}, token=ta)
    call("listening progress invalid", "PUT", f"/api/v1/me/briefings/{delivery}/progress", {"progress_seconds": 9, "duration_seconds": 3}, token=ta)
    call("listening progress not number", "PUT", f"/api/v1/me/briefings/{delivery}/progress", {"progress_seconds": "x", "duration_seconds": 3}, token=ta)
    call("history with progress", "GET", "/api/v1/me/briefings?limit=5", token=ta)
    call("audio retry when ready", "POST", f"/api/v1/me/briefings/{delivery}/audio/retry", token=ta)
    call("dev notifications enqueue", "POST", "/api/v1/dev/notifications/enqueue", token=ta)
    call("dev notifications run", "POST", "/api/v1/dev/notifications/run", token=ta)

    # Voices
    call("voices", "GET", "/api/v1/me/audio/voices", token=ta)
    # Onboarding lists the voices of the language just picked, before saving it.
    call("voices for another language", "GET", "/api/v1/me/audio/voices?language=en", token=ta)
    call("voice preview", "GET", "/api/v1/me/audio/voices/newzi_clara/preview", token=ta)
    call("voice preview for another language", "GET", "/api/v1/me/audio/voices/newzi_jenny/preview?language=en", token=ta)
    call("voice preview unknown", "GET", "/api/v1/me/audio/voices/nobody/preview", token=ta)

    # News and articles
    call("news", "GET", "/api/v1/me/news?limit=5", token=ta)
    call("news query", "GET", "/api/v1/me/news?limit=5&q=Manchete%203", token=ta)
    call("news topic", "GET", "/api/v1/me/news?limit=5&topic=ECONOMY", token=ta)
    call("news unknown topic", "GET", "/api/v1/me/news?limit=5&topic=NOPE", token=ta)
    call("news discovery", "GET", "/api/v1/me/news?limit=3&discovery=true", token=ta)
    call("content revision", "GET", "/api/v1/me/content/revision", token=ta)
    call("feedback empty", "GET", "/api/v1/me/articles/article_01/feedback", token=ta)
    call("feedback invalid", "PUT", "/api/v1/me/articles/article_01/feedback", {"rating": 9}, token=ta)
    call("feedback bool", "PUT", "/api/v1/me/articles/article_01/feedback", {"rating": True}, token=ta)
    call("feedback", "PUT", "/api/v1/me/articles/article_01/feedback", {"rating": 4}, token=ta)
    call("article image unknown", "GET", "/api/v1/articles/article_01/image", token=ta)
    call("article image without auth", "GET", "/api/v1/articles/article_01/image")

    # Saved stories and briefings
    story = {"id": "article_01", "headline": "Manchete 1", "summary": "Resumo", "primary_taxonomy_id": "ECONOMY", "sources": [{"publisher": "Fonte 1", "url": "https://news.example/1", "article_id": "article_01"}]}
    call("save story invalid", "PUT", "/api/v1/me/saved", {"story": {"id": "x"}}, token=ta)
    call("save story", "PUT", "/api/v1/me/saved", {"story": story}, token=ta)
    time.sleep(1.1)  # saved_at has one-second resolution; keep the expected order unambiguous
    call("save story 2", "PUT", "/api/v1/me/saved", {"story": {"id": "article_02", "headline": "Manchete 2", "category": "Tecnologia"}}, token=ta)
    call("saved list", "GET", "/api/v1/me/saved", token=ta)
    call("saved page", "GET", "/api/v1/me/saved?limit=1", token=ta)
    call("saved page 2", "GET", "/api/v1/me/saved?limit=1&cursor=1", token=ta)
    call("saved by topic", "GET", "/api/v1/me/saved?topic=ECONOMY", token=ta)
    call("saved progress", "PUT", "/api/v1/me/saved/article_01/progress", {"progress": 40}, token=ta)
    call("saved progress invalid", "PUT", "/api/v1/me/saved/article_01/progress", {"progress": 140}, token=ta)
    call("saved progress missing", "PUT", "/api/v1/me/saved/zzz/progress", {"progress": 10}, token=ta)
    call("saved overview", "GET", "/api/v1/me/saved/overview", token=ta)
    call("save briefing missing", "PUT", "/api/v1/me/saved-briefings", {"briefing_id": "nope"}, token=ta)
    call("save briefing", "PUT", "/api/v1/me/saved-briefings", {"briefing_id": delivery}, token=ta)
    call("saved briefings", "GET", "/api/v1/me/saved-briefings", token=ta)
    call("remove saved briefing", "DELETE", f"/api/v1/me/saved-briefings/{delivery}", token=ta)
    call("remove saved story", "DELETE", "/api/v1/me/saved/article_02", token=ta)
    call("remove saved story again", "DELETE", "/api/v1/me/saved/article_02", token=ta)

    # Devices and notification settings
    call("device invalid", "POST", "/api/v1/me/devices", {"platform": "WEB", "push_token": "abcdefghijkl"}, token=ta)
    _, device = call("device register", "POST", "/api/v1/me/devices", {"platform": "ANDROID", "push_token": "push-token-0001", "timezone": "UTC"}, token=ta)
    call("device same token other user", "POST", "/api/v1/me/devices", {"platform": "ANDROID", "push_token": "push-token-0001"}, token=tb)
    call("device delete not owner", "DELETE", f"/api/v1/me/devices/{device['id']}", token=ta)
    call("notification settings", "GET", "/api/v1/me/notification-settings", token=ta)
    call("notification settings update", "PUT", "/api/v1/me/notification-settings", {"daily_briefing_enabled": False}, token=ta)

    # Legacy per-user routes
    call("users route owner", "GET", f"/api/v1/users/{ua}", token=ta)
    call("users route other", "GET", f"/api/v1/users/{ua}/preferences", token=tb)
    call("users route anonymous", "GET", f"/api/v1/users/{ua}/preferences")

    # Preference changes drive regeneration
    call("change voice", "PUT", "/api/v1/me/preferences", {"audio_voice_id": "newzi_clara"}, token=ta)
    _, refresh = call("manual refresh", "POST", "/api/v1/me/briefings/refresh", token=ta)
    call("manual refresh coalesced", "POST", "/api/v1/me/briefings/refresh", token=ta)
    call("generation status", "GET", f"/api/v1/me/briefings/generations/{refresh['generation_id']}", token=ta)
    call("generation status other user", "GET", f"/api/v1/me/briefings/generations/{refresh['generation_id']}", token=tb)
    call("generation audio retry not failed", "POST", f"/api/v1/me/briefings/generations/{refresh['generation_id']}/audio/retry", token=ta)
    call("change topics", "PUT", "/api/v1/me/preferences", {"topics": ["ECONOMY"]}, token=ta)
    call("refresh without topics", "POST", "/api/v1/me/briefings/refresh", token=tb)

    # Development endpoints
    call("dev jobs", "GET", "/api/v1/dev/jobs", token=ta)
    call("dev diagnostic", "GET", f"/api/v1/dev/users/{ua}/briefing/diagnostic", token=ta)
    call("dev diagnostic other user", "GET", f"/api/v1/dev/users/{ua}/briefing/diagnostic", token=tb)
    call("dev audio metrics", "GET", "/api/v1/dev/audio/metrics", token=ta)
    call("dev scheduler run", "POST", "/api/v1/dev/scheduler/run", token=ta)

    # Logout
    call("logout", "POST", "/api/v1/auth/logout", token=ta)
    call("me after logout", "GET", "/api/v1/me", token=ta)
    return records


def compare(records, golden):
    """Return human-readable differences between a run and the golden records."""
    problems = []
    by_step = {entry["step"]: entry for entry in golden}
    for entry in records:
        expected = by_step.get(entry["step"])
        if expected is None:
            problems.append(f"{entry['step']}: not in golden file"); continue
        for field in ("request", "status", "body"):
            if entry[field] != expected[field]:
                problems.append(f"{entry['step']}: {field} differs\n  expected: {json.dumps(expected[field], ensure_ascii=False)[:600]}\n"
                                f"  actual:   {json.dumps(entry[field], ensure_ascii=False)[:600]}")
    missing = set(by_step) - {entry["step"] for entry in records}
    problems.extend(f"{step}: missing from run" for step in sorted(missing))
    return problems


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    import servers
    with servers.running() as (base_url, seed):
        records = run(base_url, seed)
    if "--write" in sys.argv:
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(records, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {len(records)} records to {GOLDEN}")
    else:
        problems = compare(records, json.loads(GOLDEN.read_text(encoding="utf-8")))
        print("\n".join(problems) or f"contract OK ({len(records)} requests)")
