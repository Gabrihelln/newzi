"""Run the NEWZI product API (FastAPI on uvicorn)."""
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "engine" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "backend" / "src"))

from newzi_backend.env import load_local_environment  # noqa: E402

load_local_environment()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "WARNING").upper(), format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def build_app():
    from newzi_backend.api import create_app
    return create_app()


if __name__ == "__main__":
    import uvicorn
    from newzi_backend.product_backend import ProductConfig, ProductRepository
    os.chdir(PROJECT_ROOT)
    config = ProductConfig()
    if config.app_env == "development":
        ProductRepository(config=config).create_dev_user()
    print(f"NEWZI PRODUCT API listening on http://{config.api_host}:{config.api_port}")
    # One process: the rate limiter and caches are in memory. The nginx proxy passes the client
    # address in X-Real-IP, which the API trusts only from a loopback peer.
    uvicorn.run(build_app(), host=config.api_host, port=config.api_port, proxy_headers=False,
                access_log=os.getenv("ACCESS_LOG", "false").lower() in {"1", "true", "yes"},
                log_level=os.getenv("LOG_LEVEL", "WARNING").lower())
