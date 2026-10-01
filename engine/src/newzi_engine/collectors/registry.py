from pathlib import Path
from urllib.parse import urlsplit
import yaml
from ..paths import ENGINE_CONFIG

def load_sources(path=None):
    path = path or (ENGINE_CONFIG / "sources.yaml")
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    for s in data.get("sources", []):
        s.setdefault("source_type", "PRIMARY" if any(x in s.get("id", "") for x in ("openai", "google_ai", "microsoft", "meta", "apple", "aws", "nvidia", "huggingface")) else ("SPECIALIZED" if any(x in s.get("id", "") for x in ("mit_", "techcrunch", "verge", "ars_", "wired", "engadget")) else "JOURNALISM"))
        s.setdefault("publisher_id", "techcrunch" if "techcrunch" in s.get("id", "") else ("ars" if s.get("id", "").startswith("ars_") else ("cnbc" if s.get("id", "").startswith("cnbc_") else s.get("id"))))
        s.setdefault("source_id",s.get("id")); s.setdefault("region","BR" if s.get("country")=="BR" else "GLOBAL")
        s.setdefault("domains",[urlsplit(s.get("url","")).hostname] if s.get("url") else [])
        s.setdefault("supported_topics",list(s.get("categories",[])))
        s.setdefault("reliability_score",max(0.0,min(1.0,1.0-float(s.get("trust_tier",2)-1)*0.2)))
        s.setdefault("priority",5); s.setdefault("enabled",True)
    return [s for s in data.get("sources", []) if s.get("enabled", True)]

def load_settings(path=None):
    path = path or (ENGINE_CONFIG / "settings.yaml")
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}

