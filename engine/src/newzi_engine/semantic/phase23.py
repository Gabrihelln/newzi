"""Phase 2.3 real-world shadow validation. Does not mutate the official pipeline."""
import hashlib, json, os, statistics, time
from concurrent.futures import ThreadPoolExecutor
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from .hybrid import HybridEditorialRouter
from .service import SemanticService, SemanticClusterVerifier
from newzi_engine.collectors.registry import load_sources, load_settings
from newzi_engine.collectors.rss import RSSCollector
from newzi_engine.llm.cache import LLMCache
from newzi_engine.llm.ollama import OllamaProvider
from newzi_engine.llm.hardware import detect_hardware
from newzi_engine.clustering.events import cluster_articles
from newzi_engine.paths import ENGINE_DATA, ENGINE_FIXTURES, ENGINE_OUTPUT
from newzi_engine.models import iso
from newzi_engine.storage import Store

EVENT_TYPES=("PRODUCT_ANNOUNCEMENT","COMPANY_ANNOUNCEMENT","FUNDING","ACQUISITION","REGULATION","LEGAL","RESEARCH","NEWS_EVENT","ANALYSIS","OPINION","INTERVIEW","PROMOTION","BUYING_GUIDE","HOW_TO","REVIEW","ROUNDUP","EVERGREEN")
VALID_SOURCES={"DETERMINISTIC","LLM_DISAMBIGUATION","ABSTAIN","FALLBACK"}

def _now(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def _hash(value): return hashlib.sha256(value.encode("utf-8")).hexdigest()
def detect_language(article):
    text=(article.title+" "+article.description).lower()
    scores={"EN":sum(text.count(x) for x in (" the "," and "," with "," of ")),"PT":sum(text.count(x) for x in (" de "," para "," uma "," nÃ£o "," que ")),"ES":sum(text.count(x) for x in (" el "," una "," para "," que "," los ")),"FR":sum(text.count(x) for x in (" le "," une "," des "," pour "," les "))}
    best=max(scores,key=scores.get)
    if scores[best]==0: best={"en":"EN","pt":"PT","pt-br":"PT","es":"ES","fr":"FR"}.get((article.language or "").lower(),"OTHER")
    return best if scores[best]>0 or best in {"EN","PT","ES","FR"} else "OTHER"

def snapshot_record(article):
    return {"id":article.article_id,"source":article.source_id,"source_name":article.source_name,"url_hash":_hash(article.url or article.title),"title":article.title,"description":article.description,"published_at":iso(article.published_at),"language":detect_language(article),"collected_at":iso(article.collected_at)}

def stratified_sample(articles, target=400):
    groups=defaultdict(list)
    for article in articles: groups[(article.source_id,detect_language(article))].append(article)
    ordered=[]; keys=sorted(groups,key=lambda k:(k[0],k[1])); index=0
    while len(ordered)<min(target,len(articles)) and keys:
        key=keys[index%len(keys)]; bucket=groups[key]
        if bucket: ordered.append(bucket.pop(0))
        else: keys.remove(key); index-=1
        index+=1
    return ordered

def _percentile(values,p):
    if not values: return None
    values=sorted(values); return values[min(len(values)-1,max(0,int(round((len(values)-1)*p))))]

def _safe_route(router,event):
    started=time.perf_counter()
    try: result=router.route(event,use_cache=False)
    except Exception as exc: result={"output_validity":"INVALID","classification_decision":"ABSTAIN","confidence_state":"INVALID","decision_source":"ABSTAIN","final_event_type":None,"candidate_types":[],"candidate_scores":[],"signals":[],"llm_used":False,"abstain_reason":"LLM_UNCERTAIN","semantic_failure":str(exc)}
    result["telemetry_latency_ms"]=round((time.perf_counter()-started)*1000,2); return result

def _event_payload(article):
    return {"event_id":article.article_id,"representative_title":article.title,"categories":article.categories,"content_genre":article.content_genre,"fingerprint":article.fingerprint,"articles":[{"article_id":article.article_id,"title":article.title,"description":article.description,"published_at":iso(article.published_at),"source_type":article.source_type,"source_tags":article.source_tags}]}

def _consistency(result, article):
    errors=[]; candidates=set(result.get("candidate_types",[])); final=result.get("final_event_type")
    if final and final not in candidates: errors.append("FINAL_NOT_IN_CANDIDATES")
    if result.get("decision_source") not in VALID_SOURCES: errors.append("INVALID_DECISION_SOURCE")
    if result.get("confidence_state")=="TRUSTED" and not result.get("signals"): errors.append("TRUSTED_WITHOUT_GROUNDING")
    if result.get("classification_decision")=="ABSTAIN" and final is not None: errors.append("ABSTAIN_HAS_FINAL")
    if result.get("output_validity")=="INVALID" and result.get("classification_decision")=="ABSTAIN" and result.get("abstain_reason")=="LLM_UNCERTAIN": pass
    if result.get("decision_source")=="DETERMINISTIC" and not result.get("signals"): errors.append("DETERMINISTIC_WITHOUT_PROVENANCE")
    if result.get("llm_used") and final and final not in candidates: errors.append("LLM_FINAL_NOT_ALLOWED")
    return errors

def _write_json(path,payload): Path(path).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")

def _make_blind(rows, path, template_path):
    blind=[{"audit_id":f"audit_{i:04d}","title":r["article"]["title"],"description":r["article"]["description"],"source":r["article"]["source"],"language":r["article"]["language"]} for i,r in enumerate(rows,1)]
    template=[{"audit_id":x["audit_id"],"expected_event_type":None,"acceptable_alternatives":[],"clear":None,"notes":""} for x in blind]
    _write_json(path,blind); _write_json(template_path,template)

def _make_pair_blind(pairs):
    blind=[{"audit_id":f"pair_{i:04d}","a":p["a"],"b":p["b"]} for i,p in enumerate(pairs,1)]
    template=[{"audit_id":x["audit_id"],"answer":None,"allowed":["SAME_EVENT","DIFFERENT_EVENT","UNCERTAIN"],"notes":""} for x in blind]
    _write_json(str(ENGINE_OUTPUT / "phase_2_3_pair_blind_audit.json"),blind); _write_json(str(ENGINE_OUTPUT / "phase_2_3_pair_answers.template.json"),template)

def prepare_snapshot_only(target=400,audit_size=100):
    """Create the immutable local fallback snapshot and blind sample without LLM calls."""
    articles=Store().all_articles(); sampled=stratified_sample(articles,target); snapshot=[snapshot_record(a) for a in sampled]; payload={"dataset":"RealWorldShadowSetV1","created_at":_now(),"count":len(snapshot),"dataset_hash":_hash(json.dumps(snapshot,ensure_ascii=False,sort_keys=True)),"collection_mode":"LOCAL_REAL_CORPUS_FALLBACK","source_status":[{"source":"local_store","count":len(articles),"error":"Live RSS unavailable in execution environment."}],"articles":snapshot}; _write_json(str(ENGINE_OUTPUT / "phase_2_3_real_world_snapshot.json"),payload); rows=[{"article":x} for x in snapshot[:min(audit_size,len(snapshot))]]; _make_blind(rows,str(ENGINE_OUTPUT / "phase_2_3_blind_audit.json"),str(ENGINE_OUTPUT / "phase_2_3_blind_audit_answers.template.json")); return payload

def run_phase_23(target=400, audit_size=100, pair_target=100, fixture=ENGINE_FIXTURES / "semantic_gold_v2.json"):
    out=Path(str(ENGINE_OUTPUT)); out.mkdir(parents=True,exist_ok=True); settings=load_settings(); settings={**settings,"request":{**settings.get("request",{}),"retries":0,"timeout_seconds":3}}; sources=load_sources(); collector=RSSCollector(settings); all_articles=[]; source_status=[]; collection_started=time.perf_counter()
    for source in sources:
        batch,error=collector.collect(source); all_articles.extend(batch); source_status.append({"source":source["id"],"count":len(batch),"error":error})
    collection_mode="LIVE_RSS"
    if not all_articles:
        all_articles=Store().all_articles(); collection_mode="LOCAL_REAL_CORPUS_FALLBACK"; source_status.append({"source":"local_store","count":len(all_articles),"error":"All configured RSS feeds returned no usable entries."})
    sampled=stratified_sample(all_articles,target); snapshot=[snapshot_record(a) for a in sampled]; dataset_hash=_hash(json.dumps(snapshot,ensure_ascii=False,sort_keys=True)); snapshot_payload={"dataset":"RealWorldShadowSetV1","created_at":_now(),"count":len(snapshot),"dataset_hash":dataset_hash,"collection_mode":collection_mode,"source_status":source_status,"articles":snapshot}; _write_json(out/"phase_2_3_real_world_snapshot.json",snapshot_payload)
    provider=OllamaProvider(os.getenv("OLLAMA_BASE_URL","http://localhost:11434"),"llama3.1:8b",min(float(os.getenv("LLM_TIMEOUT_SECONDS","60")),15),1); health=provider.health_check(); service=SemanticService(provider,LLMCache("data/news_engine_phase23.sqlite3"),retries=0); router=HybridEditorialRouter(service); rows=[]; telemetry=[]
    llm_timeout=min(float(os.getenv("LLM_TIMEOUT_SECONDS","60")),15)
    def route_one(article):
        worker_service=SemanticService(OllamaProvider(os.getenv("OLLAMA_BASE_URL","http://localhost:11434"),"llama3.1:8b",llm_timeout,1),LLMCache("data/news_engine_phase23.sqlite3"),retries=0)
        return article,_safe_route(HybridEditorialRouter(worker_service),_event_payload(article))
    with ThreadPoolExecutor(max_workers=1) as pool:
        for article,result in pool.map(route_one,sampled):
            record={"id":article.article_id,"article":snapshot_record(article),"result":result}; rows.append(record); telemetry.append(result["telemetry_latency_ms"])
    decisions=Counter(r["result"].get("decision_source") for r in rows); states=Counter(r["result"].get("confidence_state") for r in rows); types=Counter(r["result"].get("final_event_type") or "ABSTAIN" for r in rows); candidate_counts=Counter(len(r["result"].get("candidate_types",[])) for r in rows); languages=Counter(r["article"]["language"] for r in rows); consistency=[{"id":r["id"],"errors":_consistency(r["result"],r["article"])} for r in rows if _consistency(r["result"],r["article"])]
    distribution_warning=bool(types and max(types.values())/max(1,len(rows))>.60); metrics={"dataset":"RealWorldShadowSetV1","count":len(rows),"output_validity":sum(r["result"].get("output_validity")=="VALID" for r in rows)/max(1,len(rows)),"classified_rate":sum(r["result"].get("classification_decision")=="CLASSIFIED" for r in rows)/max(1,len(rows)),"trusted_rate":states["TRUSTED"]/max(1,len(rows)),"review_rate":states["REVIEW"]/max(1,len(rows)),"abstention_rate":states["ABSTAIN"]/max(1,len(rows)),"invalid_rate":states["INVALID"]/max(1,len(rows)),"deterministic_rate":decisions["DETERMINISTIC"]/max(1,len(rows)),"LLM_invocation_rate":sum(r["result"].get("llm_used") for r in rows)/max(1,len(rows)),"event_type_distribution":dict(types),"candidate_count_distribution":dict(candidate_counts),"average_candidates":sum(candidate_counts[k]*k for k in candidate_counts)/max(1,len(rows)),"latency_ms":{"p50_total":_percentile(telemetry,.50),"p95_total":_percentile(telemetry,.95),"p99_total":_percentile(telemetry,.99)},"language_distribution":dict(languages),"decision_source_distribution":dict(decisions),"class_distribution_warning":"CLASS_DISTRIBUTION_WARNING" if distribution_warning else None,"automated_consistency_errors":consistency}
    _write_json(out/"phase_2_3_operational_metrics.json",metrics)
    ranked=sorted(rows,key=lambda r:(r["result"].get("confidence_state") not in {"TRUSTED","REVIEW"},r["result"].get("llm_used") is False,r["id"]))[:min(audit_size,len(rows))]; _make_blind(ranked,out/"phase_2_3_blind_audit.json",out/"phase_2_3_blind_audit_answers.template.json")
    trusted=[r for r in rows if r["result"].get("confidence_state")=="TRUSTED"]; review=[r for r in rows if r["result"].get("confidence_state")=="REVIEW"]; abstain=[r for r in rows if r["result"].get("confidence_state")=="ABSTAIN"]; invalid=[r for r in rows if r["result"].get("confidence_state")=="INVALID"]
    _write_json(out/"phase_2_3_trusted_audit.json",[{"audit_id":r["id"],"title":r["article"]["title"],"description":r["article"]["description"],"source":r["article"]["source"],"language":r["article"]["language"],"predicted_event_type":r["result"].get("final_event_type"),"confidence":r["result"].get("confidence")} for r in trusted[:max(50,len(trusted))]])
    _write_json(out/"phase_2_3_abstention_audit.json",[{"id":r["id"],"title":r["article"]["title"],"reason":r["result"].get("abstain_reason"),"classification":"PENDING_HUMAN_REVIEW"} for r in abstain])
    _write_json(out/"phase_2_3_invalid_audit.json",[{"id":r["id"],"title":r["article"]["title"],"category":"PROVIDER_FAILURE" if r["result"].get("semantic_failure") else "SCHEMA_FAILURE","details":r["result"].get("semantic_failure") or r["result"].get("llm_result")} for r in invalid])
    events,_=cluster_articles(sampled,settings,sources,diagnostics=True); pairs=[]
    for event in events:
        if len(event.articles)>1:
            for a in event.articles:
                for b in event.articles:
                    if a.article_id<b.article_id: pairs.append({"a":snapshot_record(a),"b":snapshot_record(b),"pair_type":"cluster_candidate"})
    for i,a in enumerate(sampled):
        for b in sampled[i+1:]:
            if a.source_id==b.source_id and a.article_id!=b.article_id and len(pairs)<pair_target*3: pairs.append({"a":snapshot_record(a),"b":snapshot_record(b),"pair_type":"hard_negative_candidate"})
            if len(pairs)>=pair_target: break
        if len(pairs)>=pair_target: break
    pairs=pairs[:pair_target]; _make_pair_blind(pairs)
    verifier=SemanticClusterVerifier(service); pair_results=[]
    def verify_pair(pair):
        worker_service=SemanticService(OllamaProvider(os.getenv("OLLAMA_BASE_URL","http://localhost:11434"),"llama3.1:8b",llm_timeout,1),LLMCache("data/news_engine_phase23.sqlite3"),retries=0)
        worker_verifier=SemanticClusterVerifier(worker_service)
        left={"article_id":pair["a"]["id"],"title":pair["a"]["title"],"description":pair["a"]["description"],"fingerprint":{}}
        right={"article_id":pair["b"]["id"],"title":pair["b"]["title"],"description":pair["b"]["description"],"fingerprint":{}}
        try: verification=worker_verifier.verify(left,right,use_cache=False)
        except Exception as exc: verification={"status":"rejected","semantic_status":"PROVIDER_FAILED","error":str(exc)}
        return {"audit_id":pair["a"]["id"]+"__"+pair["b"]["id"],"pair_type":pair["pair_type"],"result":verification}
    with ThreadPoolExecutor(max_workers=1) as pool: pair_results=list(pool.map(verify_pair,pairs))
    _write_json(out/"phase_2_3_pair_results.json",{"count":len(pair_results),"results":pair_results,"same_event_count":sum(x["result"].get("result",{}).get("decision")=="SAME_EVENT" for x in pair_results),"different_event_count":sum(x["result"].get("result",{}).get("decision")=="DIFFERENT_EVENT" for x in pair_results),"uncertain_count":sum(x["result"].get("result",{}).get("decision")=="UNCERTAIN" for x in pair_results)})
    performance={"model":"llama3.1:8b","temperature":0.0,"cache":False,"router_version":"hybrid_editorial_router_v1","candidate_generator_version":"event_type_candidate_generator_v1","prompt_version":"hybrid_editorial_router_v1","timestamp":_now(),"hardware":detect_hardware(),"articles_per_minute":len(sampled)/max(.001,(time.perf_counter()-collection_started)/60),"dataset_hash":dataset_hash,"provider_health":health}
    _write_json(out/"phase_2_3_performance.json",performance); _write_json(out/"phase_2_3_taxonomy_gaps.json",[])
    return report


