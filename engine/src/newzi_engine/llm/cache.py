import hashlib, json, sqlite3
from datetime import datetime, timezone
from ..paths import ENGINE_DATA
class LLMCache:
    def __init__(self,path=None):
        path = path or (ENGINE_DATA / "news_engine.sqlite3")
        self.db=sqlite3.connect(path); self.db.execute("CREATE TABLE IF NOT EXISTS llm_cache(input_hash TEXT PRIMARY KEY, provider TEXT, model TEXT, prompt_version TEXT, schema_version TEXT, created_at TEXT, result_json TEXT)"); self.db.execute("CREATE TABLE IF NOT EXISTS llm_observability(id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, event_id TEXT, provider TEXT, model TEXT, prompt_version TEXT, input_size INTEGER, attempt INTEGER, latency_ms REAL, cache_hit INTEGER, validation_result TEXT, error TEXT)"); self.db.commit()
    @staticmethod
    def key(content,model,prompt_version,schema_version): return hashlib.sha256(json.dumps([content,model,prompt_version,schema_version],ensure_ascii=False).encode()).hexdigest()
    def get(self,key):
        row=self.db.execute("SELECT result_json FROM llm_cache WHERE input_hash=?",(key,)).fetchone(); return json.loads(row[0]) if row else None
    def put(self,key,meta,result): self.db.execute("INSERT OR REPLACE INTO llm_cache VALUES(?,?,?,?,?,?,?)",(key,meta["provider"],meta["model"],meta["prompt_version"],meta["schema_version"],datetime.now(timezone.utc).isoformat(),json.dumps(result,ensure_ascii=False))); self.db.commit()
    def log(self,**data): self.db.execute("INSERT INTO llm_observability(created_at,event_id,provider,model,prompt_version,input_size,attempt,latency_ms,cache_hit,validation_result,error) VALUES(datetime('now'),?,?,?,?,?,?,?,?,?,?)",(data.get("event_id",""),data.get("provider",""),data.get("model",""),data.get("prompt_version",""),data.get("input_size",0),data.get("attempt",0),data.get("latency_ms",0),int(data.get("cache_hit",False)),data.get("validation_result",""),data.get("error"))); self.db.commit()

