"""A deploy or restart kills the worker mid-collection: the next worker releases that run at once."""
import socket


def add_run(repo, run_id, owner):
    repo.db.execute("INSERT INTO content_ingestion_runs(id,status,started_at,owner) VALUES(?,'RUNNING',?,?)",
                    (run_id, "2026-10-19T14:32:02.222Z", owner))
    repo.db.commit()


def status(repo, run_id):
    return repo.db.execute("SELECT status FROM content_ingestion_runs WHERE id=?", (run_id,)).fetchone()[0]


def test_a_run_whose_process_died_is_released_when_the_worker_starts(repo, monkeypatch):
    from newzi_backend.scheduling import NewsRefreshWorker
    host = socket.gethostname()
    monkeypatch.setattr(NewsRefreshWorker, "_process_alive", staticmethod(lambda pid: pid != 4242))
    add_run(repo, "killed", f"{host}:4242")
    assert NewsRefreshWorker(repo).recover_interrupted() == 1
    assert status(repo, "killed") == "FAILED"
    # A new collection can start right away instead of waiting INGESTION_TIMEOUT_MINUTES.
    assert repo.db.execute("SELECT COUNT(*) FROM content_ingestion_runs WHERE status='RUNNING'").fetchone()[0] == 0


def test_a_run_still_alive_or_on_another_host_is_left_alone_and_a_run_without_owner_is_released(repo, monkeypatch):
    from newzi_backend.scheduling import NewsRefreshWorker
    monkeypatch.setattr(NewsRefreshWorker, "_process_alive", staticmethod(lambda pid: True))
    add_run(repo, "elsewhere", "other-host:4242")
    assert NewsRefreshWorker(repo).recover_interrupted() == 0 and status(repo, "elsewhere") == "RUNNING"
    repo.db.execute("DELETE FROM content_ingestion_runs"); repo.db.commit()
    add_run(repo, "alive", f"{socket.gethostname()}:4242")
    assert NewsRefreshWorker(repo).recover_interrupted() == 0 and status(repo, "alive") == "RUNNING"
    repo.db.execute("DELETE FROM content_ingestion_runs"); repo.db.commit()
    add_run(repo, "before_owners", None)                       # recorded by the code before this change
    assert NewsRefreshWorker(repo).recover_interrupted() == 1 and status(repo, "before_owners") == "FAILED"


def test_a_new_run_records_its_owner(repo, monkeypatch):
    from newzi_backend import scheduling
    monkeypatch.setattr(scheduling, "_engine_collect_sources", lambda: (lambda incremental=True: (_ for _ in ()).throw(RuntimeError("offline"))))
    try:
        scheduling.NewsRefreshWorker(repo).refresh_if_due(force=True)
    except RuntimeError:
        pass
    owner = repo.db.execute("SELECT owner FROM content_ingestion_runs ORDER BY started_at DESC LIMIT 1").fetchone()[0]
    assert owner == scheduling.NewsRefreshWorker.owner()
