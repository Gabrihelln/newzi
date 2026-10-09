"""Start the product API (FastAPI on uvicorn) on a free local port against a fresh database."""
import contextlib
import socket
import threading
import time

import support


def _free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0)); return probe.getsockname()[1]


@contextlib.contextmanager
def running(database_url=None):
    """Yield ``(base_url, seed)``; ``seed(topics)`` indexes test content in the server's database."""
    support.fresh_environment(database_url)
    support.install_fake_tts()
    import uvicorn
    from newzi_backend.api import create_app
    from newzi_backend.product_backend import ProductConfig, ProductRepository, ProductService
    if database_url:
        support.reset_postgres(database_url)
    app = create_app(ProductService(ProductRepository(config=ProductConfig())))
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", proxy_headers=False))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline: raise RuntimeError("API server did not start")
        time.sleep(0.02)

    def seed(topics):
        repo = app.state.service.repo
        try: support.seed_content(repo, tuple(topics))
        finally: repo.close_thread_connection()
    try:
        yield f"http://127.0.0.1:{port}", seed
    finally:
        server.should_exit = True; thread.join(timeout=10)
        app.state.service.repo.close_thread_connection()
