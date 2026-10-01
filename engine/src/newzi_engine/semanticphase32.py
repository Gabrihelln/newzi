import json, os, re, statistics, time, uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from newzi_engine.llm.cache import LLMCache
from newzi_engine.llm.ollama import OllamaProvider
from newzi_engine.semantic.service import SemanticService
from newzi_engine.storage import Store
from .acquisition import ArticleContentResolver, build_evidence_pack
from .summarizer import SemanticSummarizer
from newzi_engine.paths import ENGINE_DATA, ENGINE_OUTPUT

class SummaryQualityGate:
    def evaluate(self,result):
        if result.get("status")!="VALID" or not result.get("result"): return {"status":"QUALITY_REJECT","errors":["SUMMARY_NOT_VALID"]}
        value=result["result"]; errors=[]; headline=value.get("headline",""); summary=value.get("summary",""); points=value.get("key_points",[])
        if not headline.strip(): errors.append("EMPTY_HEADLINE")
        if not summary.strip(): errors.append("EMPTY_SUMMARY")
        if not 40<=len(summary.split())<=150: errors.append("SUMMARY_LENGTH")
        if len(points)!=len({p.strip().casefold() for p in points}): errors.append("DUPLICATE_KEY_POINTS")
        if any(len(p.split())<2 for p in points): errors.append("BROKEN_KEY_POINT")
        if summary and max(Counter(summary.casefold().split()).values())>max(5,len(summary.split())//4): errors.append("REPETITION")
        return {"status":"QUALITY_PASS" if not errors else "QUALITY_REJECT","errors":errors}

class DailyBriefingComposer:
    def compose(self,items,target_count=10):
        accepted=[x for x in items if x.get("summary_status")=="VALID" and x.get("quality_status")=="QUALITY_PASS"]; accepted=accepted[:target_count]; counts={"publisher":Counter(),"category":Counter(),"event_type":Counter()}
        out=[]
        for item in accepted:
            value=item["summary"]; counts["publisher"].update(a.get("publisher","") for a in item["evidence_pack"]["articles"]); counts["category"].update(item.get("categories",[])); counts["event_type"].update([item.get("event_type") or "UNKNOWN"]); out.append({"rank_original":item["rank_original"],"event_id":item["event_id"],"headline":value.get("headline"),"summary":value.get("summary"),"why_it_matters":value.get("why_it_matters"),"key_points":value.get("key_points"),"sources":[{"publisher":a.get("publisher"),"url":a.get("url"),"published_at":a.get("published_at")} for a in item["evidence_pack"]["articles"]],"confidence":value.get("confidence")})
        return {"briefing_id":f"briefing_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}","generated_at":datetime.now(timezone.utc).isoformat(),"target_count":target_count,"actual_count":len(out),"events_considered":len(items),"events_rejected":sum(x.get("summary_status")!="VALID" or x.get("quality_status")!="QUALITY_PASS" for x in items),"events_backfilled":max(0,len(out)-target_count),"publisher_distribution":dict(counts["publisher"]),"category_distribution":dict(counts["category"]),"event_type_distribution":dict(counts["event_type"]),"items":out}

def _event_from_item(item,by_url,by_title):
    articles=[]
    for a in item.get("articles",[]):
        full=by_url.get(a.get("url")) or by_title.get(a.get("title","") )
        articles.append({"title":a.get("title",""),"description":full.description if full else "","source":a.get("source",""),"publisher_id":a.get("publisher_id",""),"published_at":a.get("published_at"),"url":a.get("url","")})
    return {"event_id":item.get("event_id"),"representative_title":item.get("title",""),"articles":articles,"primary_entities":item.get("primary_entities",[]),"content_genre":item.get("content_genre"),"categories":item.get("categories",[])}

def run_phase32(target_count=None,briefing_path=str(ENGINE_OUTPUT / "briefing.json")):
    target_count=target_count or int(os.getenv("BRIEFING_TARGET_COUNT","10")); briefing=json.loads(Path(briefing_path).read_text(encoding="utf-8")); store=Store(); corpus=store.all_articles(); by_url={a.url:a for a in corpus}; by_title={a.title:a for a in corpus}; ranked=briefing.get("items",[]); resolver=ArticleContentResolver(); model=os.getenv("OLLAMA_MODEL","llama3.1:8b"); provider=OllamaProvider(os.getenv("OLLAMA_BASE_URL","http://localhost:11434"),model,min(float(os.getenv("LLM_TIMEOUT_SECONDS","60")),20),1); service=SemanticService(provider,LLMCache("data/news_engine_summary.sqlite3"),retries=1); summarizer=SemanticSummarizer(service); gate=SummaryQualityGate(); started=time.perf_counter(); audits=[]; considered=ranked[:max(target_count*2,target_count)]
    for item in considered:
        event=_event_from_item(item,by_url,by_title); pack=build_evidence_pack(event,resolver)
        if pack["event_evidence_quality"]=="LOW": summary={"status":"ABSTAIN","result":None,"validation_status":"INSUFFICIENT_EVIDENCE","grounding_errors":["INSUFFICIENT_EVIDENCE"]}
        else:
            enriched={**event,"articles":[{"title":a["title"],"description":next((p["evidence_text"] for p in pack["articles"] if p["article_id"]==f"article_{i+1:02d}"),""),"source":a.get("source",a.get("source_name","")),"publisher_id":a.get("publisher_id",""),"published_at":a.get("published_at"),"url":a.get("url","")} for i,a in enumerate(event["articles"])]}; summary=summarizer.summarize(enriched,use_cache=False)
        quality=gate.evaluate(summary); audits.append({"rank_original":item.get("rank"),"event_id":item.get("event_id"),"title":item.get("title"),"categories":item.get("categories",[]),"event_type":item.get("content_genre"),"input_original":event,"evidence_pack":pack,"summary":summary.get("result"),"summary_status":summary.get("status"),"validation_status":summary.get("validation_status"),"grounding_errors":summary.get("grounding_errors",[]),"quality_status":quality["status"],"quality_errors":quality["errors"],"latency_ms":summary.get("latency_ms")})
    composed=DailyBriefingComposer().compose(audits,target_count); out=Path(str(ENGINE_OUTPUT)); out.mkdir(parents=True,exist_ok=True); (out/"daily_briefing_v1.json").write_text(json.dumps(composed,ensure_ascii=False,indent=2),encoding="utf-8"); lines=["SEU BRIEFING DE TECNOLOGIA",datetime.now().strftime("%d de %B de %Y"),""]
    for i,item in enumerate(composed["items"],1): lines += [f"{i}. {item['headline']}","",item["summary"],""]+(["Por que importa:",item["why_it_matters",""]] if item.get("why_it_matters") else [])+["Pontos principais:"]+[f"Ã¢â‚¬Â¢ {x}" for x in item["key_points"]]+["","Fontes:"]+[f"- {x['publisher']} Ã¢â‚¬â€ {x['url']}" for x in item["sources"]]+[""]
    (out/"daily_briefing_v1.md").write_text("\n".join(lines),encoding="utf-8"); (out/"phase_3_2_evidence_audit.json").write_text(json.dumps(audits,ensure_ascii=False,indent=2),encoding="utf-8"); (out/"phase_3_2_human_audit.json").write_text(json.dumps([{"event_id":x["event_id"],"headline":(x.get("summary") or {}).get("headline"),"summary":(x.get("summary") or {}).get("summary"),"factual_accuracy":None,"natural_portuguese":None,"usefulness":None,"headline_quality":None,"why_it_matters_quality":None,"would_read":None,"human_notes":None} for x in audits if x.get("summary")],ensure_ascii=False,indent=2),encoding="utf-8"); valid=[x for x in audits if x["summary_status"]=="VALID"]; metrics={"events_considered":len(audits),"evidence_acquisition_success":sum(x["evidence_pack"]["event_evidence_quality"] in {"HIGH","MEDIUM"} for x in audits)/max(1,len(audits)),"evidence_quality_distribution":dict(Counter(x["evidence_pack"]["event_evidence_quality"] for x in audits)),"summaries_attempted":sum(x["summary_status"] not in {"ABSTAIN","INSUFFICIENT_EVIDENCE"} for x in audits),"valid":len(valid),"insufficient_evidence":sum(x["validation_status"]=="INSUFFICIENT_EVIDENCE" for x in audits),"invalid":sum(x["summary_status"]=="INVALID" for x in audits),"quality_reject":sum(x["quality_status"]=="QUALITY_REJECT" for x in audits),"quality_pass_rate":sum(x["quality_status"]=="QUALITY_PASS" for x in valid)/max(1,len(valid)),"average_latency_ms":statistics.mean([x["latency_ms"] for x in audits if x.get("latency_ms")]) if any(x.get("latency_ms") for x in audits) else None,"final_briefing_count":composed["actual_count"]}; (out/"phase_3_2_metrics.json").write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding="utf-8"); status={"PHASE_1":"FROZEN","PHASE_2":"SHADOW / VALIDATION_PENDING","PHASE_3_1":"COMPLETE","PHASE_3_2":"COMPLETE","READY_FOR_PRODUCTION":"NO","READY_FOR_PHASE_3_3":"PENDING_HUMAN_AUDIT","metrics":metrics,"changes":["ArticleContentResolver","evidence_pack_v1","SummaryQualityGate","DailyBriefingComposer","rank-preserving backfill"]}; Path("REPORT_PHASE_3_2.md").write_text("# NEWS ENGINE Ã¢â‚¬â€ FASE 3.2\n\n"+json.dumps(status,ensure_ascii=False,indent=2)+"\n\nThe final briefing contains only VALID and QUALITY_PASS summaries. Human audit remains pending.",encoding="utf-8"); return status


