"""Run the edition audio worker without blocking briefing delivery."""
import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "engine" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "backend" / "src"))

from newzi_backend.audio import AudioService
from newzi_backend.env import load_local_environment
from newzi_backend.product_backend import ProductConfig, ProductRepository


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="process one pending audio job")
    args = parser.parse_args()
    load_local_environment()
    repo = ProductRepository(config=ProductConfig())
    if not repo.config.audio_enabled:
        raise SystemExit("AUDIO_ENABLED=false")
    service = AudioService(repo)
    if args.once:
        queued = service.enqueue_ready_editions()
        result=service.generate_pending()
        from newzi_backend.notifications import NotificationService
        notifications=NotificationService(repo); enqueued=notifications.enqueue_ready(); sent=notifications.run_once()
        print(json.dumps({"audio_jobs_created": queued, **result,"notifications_enqueued":enqueued,"notification_delivery":sent}, ensure_ascii=False))
    else:
        service.run_forever()
