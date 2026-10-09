"""Run the local NEWS ENGINE product API."""
import json
import logging
import os
import traceback
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "engine" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "backend" / "src"))
from newzi_backend.product_backend import ProductAPI, ProductConfig, ProductRepository


def load_local_environment():
    """Load simple local .env values without overriding explicit process env."""
    env_path = PROJECT_ROOT / '.env'
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key == 'GOOGLE_APPLICATION_CREDENTIALS' and value and not Path(value).is_absolute():
            value = str((PROJECT_ROOT / value).resolve())
        if key:
            os.environ.setdefault(key, value)


load_local_environment()
logging.basicConfig(level=os.getenv('LOG_LEVEL','WARNING').upper(), format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
MAX_BODY_BYTES = 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    api = ProductAPI(ProductRepository(config=ProductConfig()))
    def _headers_for_api(self):
        request_id = self.headers.get('X-Newzi-Debug-Request-Id', '')
        if self.api.config.app_env == 'development':
            names = ','.join(str(name) for name in self.headers.keys())
            print(f"[Backend HTTP {request_id or 'none'}] received")
            print(f"[Backend HTTP {request_id or 'none'}] header_names={names}")
        return {str(name).lower(): value for name, value in self.headers.items()}
    def _client_ip(self):
        peer = self.client_address[0] if self.client_address else ''
        # Only a local reverse proxy (deploy/nginx sets X-Real-IP) may name the real client;
        # a direct client cannot spoof its address through the header.
        if peer in ('127.0.0.1', '::1', '::ffff:127.0.0.1'):
            forwarded = (self.headers.get('X-Real-IP') or '').strip()
            if forwarded: return forwarded
        return peer
    def _api(self, method, body=None):
        try:
            return self.api.handle(method, self.path, body, self._headers_for_api(), client_ip=self._client_ip())
        finally:
            # Each request runs on its own thread; release that thread's SQLite connection.
            self.api.repo.close_thread_connection()
    def _send(self, status, value):
        if status == 204:
            self.send_response(204); self.end_headers(); return
        raw=json.dumps(value,ensure_ascii=False).encode("utf-8"); self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        status, payload = self._api("GET")
        if status == 200 and isinstance(payload, dict) and isinstance(payload.get("_image_bytes"), bytes):
            raw=payload["_image_bytes"]
            self.send_response(200); self.send_header("Content-Type",payload.get("mime_type","image/jpeg")); self.send_header("Content-Length",str(len(raw))); self.send_header("Cache-Control","private, max-age=86400"); self.send_header("X-Content-Type-Options","nosniff"); self.end_headers(); self.wfile.write(raw)
            return
        if status == 200 and isinstance(payload, dict) and payload.get("_audio_path"):
            path = Path(payload["_audio_path"]).resolve()
            root = self.api.audio.storage.root
            if root not in path.parents or not path.is_file(): self._send(404, {"error": "not_found"}); return
            self.send_response(200); self.send_header("Content-Type", payload.get("mime_type", "audio/wav")); self.send_header("Content-Length", str(path.stat().st_size)); self.send_header("Cache-Control", "private, max-age=3600"); self.end_headers()
            with path.open("rb") as source:
                while chunk := source.read(64 * 1024): self.wfile.write(chunk)
            return
        self._send(status, payload)
    def do_PUT(self): self._json("PUT")
    def do_POST(self): self._json("POST")
    def do_DELETE(self): self._json("DELETE")
    def _json(self, method):
        try: length=int(self.headers.get("Content-Length") or 0)
        except ValueError: self._send(400,{"error":"invalid_content_length"}); return
        if length<0 or length>MAX_BODY_BYTES: self._send(413,{"error":"payload_too_large"}); return
        try: body=json.loads(self.rfile.read(length) or b"{}")
        except Exception: self._send(400,{"error":"invalid_json"}); return
        self._send(*self._api(method,body))
    def log_message(self,*args): return

if __name__ == "__main__":
    os.chdir(PROJECT_ROOT)
    config=ProductConfig(); ProductRepository(config=config).create_dev_user(); print(f"NEWZI PRODUCT API listening on http://{config.api_host}:{config.api_port}"); ThreadingHTTPServer((config.api_host,config.api_port),Handler).serve_forever()

