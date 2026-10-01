import json, os, statistics, time
from pathlib import Path
from newzi_engine.llm.cache import LLMCache
from newzi_engine.llm.ollama import OllamaProvider
from newzi_engine.storage import Store
from .summarizer import SemanticSummarizer
from newzi_engine.paths import ENGINE_DATA, ENGINE_OUTPUT

def _event_from_item(item, by_url, by_title):
    articles=[]
    for a in item.get("articles",[]):
        full=by_url.get(a.get("url")) or by_title.get(a.get("title","") )
        articles.append({"title":a.get("title",""),"description":(full.description[:3000] if full else ""),"source":a.get("source",""),"publisher_id":a.get("publisher_id",""),"published_at":a.get("published_at"),"url":a.get("url","")})
    return {"event_id":item.get("event_id"),"representative_title":item.get("title",""),"articles":articles,"primary_entities":item.get("primary_entities",[]),"content_genre":item.get("content_genre"),"categories":item.get("categories",[])}

def _metrics(results):
    n=len(results); valid=[r for r in results if r.get("status")=="VALID"]; statuses={s:sum(r.get("status")==s for r in results) for s in ("VALID","REVIEW","ABSTAIN","INVALID","PROVIDER_FAILED")}; lats=[r.get("latency_ms") for r in results if isinstance(r.get("latency_ms"),(int,float))]; ins=[r.get("input_tokens") for r in results if isinstance(r.get("input_tokens"),(int,float))]; outs=[r.get("output_tokens") for r in results if isinstance(r.get("output_tokens"),(int,float))]; codes=[c for r in results for c in r.get("grounding_errors",[])]
    return {"count":n,"schema_validity":sum(r.get("validation_status") in {"VALID","REVIEW","ABSTAINED"} for r in results)/max(1,n),"grounding_validity":sum(not any(c.endswith("HALLUCINATION") or c in {"NUMBER_HALLUCINATION","DATE_HALLUCINATION","AMOUNT_HALLUCINATION","PERCENTAGE_HALLUCINATION"} for c in r.get("grounding_errors",[])) for r in valid)/max(1,len(valid)),"number_preservation":sum(not any(c in {"NUMBER_HALLUCINATION","AMOUNT_HALLUCINATION","DATE_HALLUCINATION","PERCENTAGE_HALLUCINATION"} for c in r.get("grounding_errors",[])) for r in valid)/max(1,len(valid)),"entity_grounding":sum("ENTITY_HALLUCINATION" not in r.get("grounding_errors",[]) for r in valid)/max(1,len(valid)),"source_attribution_validity":sum("SOURCE_REF_INVALID" not in r.get("grounding_errors",[]) for r in valid)/max(1,len(valid)),"abstention_rate":statuses["ABSTAIN"]/max(1,n),"invalid_rate":statuses["INVALID"]/max(1,n),"provider_failure_rate":statuses["PROVIDER_FAILED"]/max(1,n),"average_latency_ms":statistics.mean(lats) if lats else None,"p95_latency_ms":sorted(lats)[max(0,int(len(lats)*.95)-1)] if lats else None,"average_input_tokens":statistics.mean(ins) if ins else None,"average_output_tokens":statistics.mean(outs) if outs else None,"statuses":statuses,"grounding_error_counts":dict(__import__('collections').Counter(codes))}

def run_phase31(count=10, briefing_path=None):
    briefing_path = briefing_path or str(ENGINE_OUTPUT / "briefing.json")
    briefing=json.loads(Path(briefing_path).read_text(encoding="utf-8")); store=Store(); corpus=store.all_articles(); by_url={a.url:a for a in corpus}; by_title={a.title:a for a in corpus}; items=briefing.get("items",[])[:count]; events=[_event_from_item(i,by_url,by_title) for i in items]; model=os.getenv("OLLAMA_MODEL","llama3.1:8b"); provider=OllamaProvider(os.getenv("OLLAMA_BASE_URL","http://localhost:11434"),model,min(float(os.getenv("LLM_TIMEOUT_SECONDS","60")),20),1); service=__import__('newzi_engine.semantic.service',fromlist=['SemanticService']).SemanticService(provider,LLMCache("data/news_engine_summary.sqlite3"),retries=1); summarizer=SemanticSummarizer(service); started=time.perf_counter(); results=[]
    for event in events:
        result=summarizer.summarize(event,target_language="pt-BR",use_cache=False); results.append(result)
    metrics=_metrics(results); out=Path(str(ENGINE_OUTPUT)); out.mkdir(parents=True,exist_ok=True); payload={"phase":"3.1","model":model,"temperature":0.0,"cache":False,"prompt_version":summarizer.prompt_version,"schema_version":summarizer.schema_version,"events":events,"results":results,"metrics":metrics,"total_latency_ms":round((time.perf_counter()-started)*1000,2)}; (out/"summary_phase_3_1_evaluation.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# SEU BRIEFING DE TECNOLOGIA","",f"Gerado em {__import__('datetime').datetime.now().isoformat()}",""]
    for i,(item,result) in enumerate(zip(items,results),1):
        value=result.get("result") or {}; lines += [f"## {i}. {value.get('headline') or item.get('title')}","",value.get("summary") or "Resumo indispon?vel: "+result.get("status","UNKNOWN"),""]
        if value.get("why_it_matters"): lines += ["**Por que importa:** "+value["why_it_matters"],""]
        if value.get("key_points"): lines += ["**Pontos-chave:**"]+[f"- {p}" for p in value["key_points"]]+[""]
        lines += ["**Fontes:**"]+[f"- {a.get('source','')} â€” {a.get('url','')}" for a in item.get("articles",[])]+[""]
    (out/"daily_briefing_experimental.md").write_text("\n".join(lines),encoding="utf-8"); (out/"daily_briefing_experimental.json").write_text(json.dumps({"title":"Seu briefing de tecnologia","items":[{"rank":i,"event_id":item.get("event_id"),"summary":result.get("result"),"status":result.get("status"),"sources":item.get("articles",[])} for i,(item,result) in enumerate(zip(items,results),1)]},ensure_ascii=False,indent=2),encoding="utf-8")
    audit=[{"event_id":r["event_id"],"headline":(r.get("result") or {}).get("headline"),"summary":(r.get("result") or {}).get("summary"),"why_it_matters":(r.get("result") or {}).get("why_it_matters"),"key_points":(r.get("result") or {}).get("key_points",[]),"sources":next((e["articles"] for e in events if e["event_id"]==r["event_id"]),[]),"factual_accuracy":None,"completeness":None,"clarity":None,"usefulness":None,"translation_quality":None,"hallucination_found":None,"human_notes":None} for r in results]; (out/"summary_human_audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    gates={"schema_validity":(metrics["schema_validity"] or 0)>=.98,"grounding_validity":(metrics["grounding_validity"] or 0)>=.95,"number_preservation":(metrics["number_preservation"] or 0)>=.99,"entity_grounding":(metrics["entity_grounding"] or 0)>=.98,"provider_failure_rate":metrics["provider_failure_rate"]==0,"invalid_rate":metrics["invalid_rate"]<=.05}; report={"architecture":"SemanticSummarizer + SummaryGroundingValidator","metrics":metrics,"gates":gates,"events_processed":len(events),"limitations":["Human factuality audit is pending.","Briefing is shadow-only.","Gold V1 is regression scaffolding, not a lexical ROUGE target."],"status":"PHASE_3_1_COMPLETE","ready_for_phase_3_2":"YES" if all(gates.values()) and metrics["count"] else "NO","ready_for_production":"NO"}; return report


