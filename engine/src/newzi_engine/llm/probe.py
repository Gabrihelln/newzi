import json, os
from pathlib import Path
from .hardware import detect_hardware
from .ollama import OllamaProvider
from .service import SemanticProbe, PROMPT_VERSION
from .validation import SCHEMA_VERSION
from ..storage import Store
from newzi_engine.paths import ENGINE_OUTPUT

def run_probe(output_dir=None):
    output_dir = output_dir or str(ENGINE_OUTPUT)
    hardware=detect_hardware(); provider_name=os.getenv("LLM_PROVIDER","ollama"); model=os.getenv("OLLAMA_MODEL",""); provider=OllamaProvider(os.getenv("OLLAMA_BASE_URL","http://localhost:11434"),model,float(os.getenv("LLM_TIMEOUT_SECONDS","60")),int(os.getenv("LLM_MAX_RETRIES","2")))
    health=provider.health_check() if provider_name=="ollama" else {"available":False,"error":f"unsupported provider: {provider_name}","models":[]}; results=[]
    if health.get("available") and not model: health={**health,"available":False,"error":"Ollama is available but OLLAMA_MODEL is not configured; no model was selected or downloaded."}
    articles=Store().all_articles()[:5]
    if health.get("available"):
        service=SemanticProbe(provider)
        for article in articles:
            content=f"Title: {article.title}\nDescription: {article.description[:1200]}"
            results.append({"event_id":article.article_id,"title":article.title,"result":service.run(article.article_id,content)})
    else:
        results=[{"event_id":a.article_id,"title":a.title,"result":{"status":"skipped","reason":health.get("error")}} for a in articles]
    payload={"provider":provider_name,"model":model,"hardware":hardware,"health":health,"prompt_version":PROMPT_VERSION,"schema_version":SCHEMA_VERSION,"cases":results}
    path=Path(output_dir); path.mkdir(parents=True,exist_ok=True); (path/"semantic_probe.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# Semantic Probe",f"Provider: {provider_name}",f"Model: {model or '(not configured)'}",f"Available: {health.get('available')}","", "## Hardware", ""]+[f"- {k}: {v}" for k,v in hardware.items()]+["", "## Cases", ""]
    for case in results: lines += [f"### {case['title']}",f"- Status: {case['result'].get('status')}",f"- Details: {case['result']}",""]
    (path/"semantic_probe.md").write_text("\n".join(lines),encoding="utf-8"); return payload


