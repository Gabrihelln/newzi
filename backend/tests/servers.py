"""Start the product API on a free local port against a fresh database."""
import contextlib
import threading

import support


@contextlib.contextmanager
def running(database_url=None):
    """Yield ``(base_url, seed)``; ``seed(topics)`` indexes test content in the server's database."""
    support.fresh_environment(database_url)
    support.install_fake_tts()
    from http.server import ThreadingHTTPServer
    import product_api
    from newzi_backend.product_backend import ProductAPI, ProductConfig, ProductRepository
    product_api.Handler.api = ProductAPI(ProductRepository(config=ProductConfig()))
    server = ThreadingHTTPServer(("127.0.0.1", 0), product_api.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()

    def seed(topics):
        repo = ProductRepository(config=ProductConfig())
        try: support.seed_content(repo, tuple(topics))
        finally: repo.close_thread_connection()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", seed
    finally:
        server.shutdown(); server.server_close()
