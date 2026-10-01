"""Run the local NEWS ENGINE product API."""
import json
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


class Handler(BaseHTTPRequestHandler):
    api = ProductAPI(ProductRepository(config=ProductConfig()))
    def _headers_for_api(self):
        request_id = self.headers.get('X-Newzi-Debug-Request-Id', '')
        if self.api.config.app_env == 'development':
            names = ','.join(str(name) for name in self.headers.keys())
            print(f"[Backend HTTP {request_id or 'none'}] received")
            print(f"[Backend HTTP {request_id or 'none'}] header_names={names}")
        return {str(name).lower(): value for name, value in self.headers.items()}
    def _send(self, status, value):
        raw=json.dumps(value,ensure_ascii=False).encode("utf-8"); self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        status, payload = self.api.handle("GET", self.path, headers=self._headers_for_api())
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
    def _json(self, method):
        try: body=json.loads(self.rfile.read(int(self.headers.get("Content-Length",0)) or 0) or b"{}")
        except Exception: self._send(400,{"error":"invalid_json"}); return
        self._send(*self.api.handle(method,self.path,body,self._headers_for_api()))
    def log_message(self,*args): return


if __name__ == "__main__":
    os.chdir(PROJECT_ROOT)
    config=ProductConfig(); ProductRepository(config=config).create_dev_user(); print(f"NEWZI PRODUCT API listening on http://{config.api_host}:{config.api_port}"); ThreadingHTTPServer((config.api_host,config.api_port),Handler).serve_forever()

