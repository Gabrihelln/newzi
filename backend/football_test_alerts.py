"""Send the four team alerts to one account as a test (kickoff, goal, final result, team news).

    python backend/football_test_alerts.py EMAIL [--team NAME]

They are built by the same code as the real alerts (football_alerts.py) with the account's first favourite team
(or --team) against a rival of the same competition, queued like real ones and delivered by the worker's
notifications role within seconds. The account's switches and devices are respected: anything turned off is
reported as skipped. Each run uses new delivery ids, so it can be repeated.
"""
import argparse
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "engine" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "backend" / "src"))

from newzi_backend.env import load_local_environment  # noqa: E402

load_local_environment()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("email")
    parser.add_argument("--team", help="team name; default: the account's first favourite team")
    args = parser.parse_args()
    os.chdir(PROJECT_ROOT)

    from newzi_backend.product_backend import ProductRepository
    from newzi_backend.football_alerts import FootballAlertService, FOOTBALL_TOPICS
    from newzi_backend.notifications import NotificationService, wants
    from newzi_backend.timeutil import utc_now
    repo = ProductRepository()
    user = repo.db.execute("SELECT id FROM users WHERE lower(email)=lower(?)", (args.email,)).fetchone()
    if not user:
        sys.exit(f"no account with e-mail {args.email}")
    uid = user["id"]
    if args.team:
        team = repo.db.execute("SELECT * FROM football_teams WHERE lower(name) LIKE lower(?) ORDER BY name LIMIT 1", (f"%{args.team}%",)).fetchone()
    else:
        team = repo.db.execute("""SELECT t.* FROM user_favorite_teams f JOIN football_teams t ON t.id=f.team_id
            WHERE f.user_id=? ORDER BY f.position LIMIT 1""", (uid,)).fetchone()
    if not team:
        sys.exit("no team: mark a favourite team in Esportes › Times favoritos, or pass --team NAME")
    import json
    code = (json.loads(team["competitions"] or "[]") or ["BSA"])[0]
    rival = repo.db.execute("SELECT * FROM football_teams WHERE id<>? AND competitions LIKE ? ORDER BY name LIMIT 1", (team["id"], f'%"{code}"%')).fetchone()
    devices = repo.db.execute("SELECT COUNT(*) FROM push_devices WHERE user_id=? AND enabled=1 AND invalidated_at IS NULL", (uid,)).fetchone()[0]
    print(f"account {args.email}: {devices} active device(s); team {team['name']} x {rival['name'] if rival else '?'} ({code})")
    if not devices:
        print("  no active device: open the app with notifications allowed, then run again")

    service = FootballAlertService(repo)
    stamp = str(int(time.time()))
    side = lambda row: {"id": row["id"], "shortName": row["name"], "tla": row["tla"], "crest": row["crest_url"]}
    match = {"id": 900000000 + int(stamp) % 1000000, "status": "IN_PLAY", "matchday": 31, "competition": {"code": code},
             "homeTeam": side(team), "awayTeam": side(rival) if rival else {"id": 0, "shortName": "Rival"}}
    previous = {"status": "TIMED", "home_goals": 0, "away_goals": 0}
    events = service._events(match, previous, "IN_PLAY", 1, 0)                      # kickoff + goal
    events += service._events(match, {"status": "IN_PLAY", "home_goals": 1, "away_goals": 0}, "FINISHED", 1, 0)
    teams = {team["id"]: {uid}}
    settings = NotificationService(repo).settings(uid)
    now = utc_now()
    for kind, payload, key in events:
        payload = service._personal(kind, payload, match, uid, teams)
        if not wants(settings, kind):
            print(f"  {kind}: skipped (switched off)"); continue
        created = service._enqueue(uid, kind, f"test:{stamp}:{key}", payload, now)
        print(f"  {kind}: queued for {created} device(s) — {payload['title']} / {payload['body']}")

    article = repo.db.execute(f"""SELECT c.id,c.title,c.description FROM indexed_content c JOIN content_taxonomy t ON t.content_id=c.id
        WHERE t.taxonomy_id IN ({','.join('?' for _ in FOOTBALL_TOPICS)}) ORDER BY c.published_at DESC LIMIT 1""", FOOTBALL_TOPICS).fetchone()
    if not wants(settings, "TEAM_NEWS"):
        print("  TEAM_NEWS: skipped (switched off)")
    elif article:
        from newzi_backend.breaking import story_summary
        payload = {"title": article["title"], "body": story_summary(article["title"], [article["description"]]) or "Toque para ler.",
                   "data": {"story_id": article["id"], "team_id": str(team["id"])}}
        created = service._enqueue(uid, "TEAM_NEWS", f"test:{stamp}:news", payload, now)
        print(f"  TEAM_NEWS: queued for {created} device(s) — {payload['title']}")
    print("The worker sends them in a few seconds (notifications role). Tap the game alerts to open Esportes; the news opens the story.")


if __name__ == "__main__":
    main()
