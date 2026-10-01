import json, re, statistics, time
from datetime import datetime
from pathlib import Path
from .summarizer import SummaryGroundingValidator
from .summarizer import SemanticSummarizer
from .entity import EntityGroundingValidatorV2
from newzi_engine.paths import ENGINE_DATA, ENGINE_OUTPUT

def _sentences(text): return len([x for x in re.split(r"(?<=[.!?])\s+",text.strip()) if x])
def audit_quality_failures(path=str(ENGINE_OUTPUT / "phase_3_2_evidence_audit.json")):
    rows=json.loads(Path(path).read_text(encoding="utf-8")); failures=[]
    for row in rows:
        if row.get("summary_status")!="VALID" or row.get("quality_status")!="QUALITY_REJECT": continue
        summary=row.get("summary") or {}; text=summary.get("summary",""); reasons=row.get("quality_errors",[]); cause="TOO_SHORT" if "SUMMARY_LENGTH" in reasons and len(text.split())<45 else ("TOO_LONG" if "SUMMARY_LENGTH" in reasons else ("REPETITIVE" if "DUPLICATE_KEY_POINTS" in reasons or "REPETITION" in reasons else ("WEAK_KEY_POINTS" if "BROKEN_KEY_POINT" in reasons else "STRUCTURAL_FAILURE")))
        failures.append({"event_id":row.get("event_id"),"headline":summary.get("headline"),"summary":text,"key_points":summary.get("key_points",[]),"why_it_matters":summary.get("why_it_matters"),"quality_reasons":reasons,"summary_character_count":len(text),"summary_word_count":len(text.split()),"sentence_count":_sentences(text),"key_point_count":len(summary.get("key_points",[])),"evidence_quality":row.get("evidence_pack",{}).get("event_evidence_quality"),"confidence":summary.get("confidence"),"primary_cause":cause})
    report={"count":len(failures),"failures":failures,"cause_distribution":{cause:sum(x["primary_cause"]==cause for x in failures) for cause in ("TOO_SHORT","TOO_LONG","REPETITIVE","BROKEN_PORTUGUESE","WEAK_HEADLINE","WEAK_KEY_POINTS","STRUCTURAL_FAILURE","OTHER")}}
    Path(str(ENGINE_OUTPUT / "phase_3_2_1_quality_failure_analysis.json")).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8"); return report

class SummaryQualityGateV2:
    """Editorial gate: hard failures reject; length and optional fields warn."""
    def evaluate(self,result):
        if result.get("status")!="VALID" or not result.get("result"): return {"status":"HARD_REJECT","hard_reasons":["FACTUAL_INVALID"],"soft_warnings":[]}
        value=result["result"]; hard=[]; soft=[]; headline=value.get("headline",""); summary=value.get("summary",""); points=value.get("key_points",[])
        if not headline.strip(): hard.append("EMPTY_HEADLINE")
        if not summary.strip(): hard.append("EMPTY_SUMMARY")
        if not isinstance(points,list) or not 2<=len(points)<=4: hard.append("STRUCTURE_INVALID")
        if summary and summary[-1] not in ".!?Ã¢â‚¬Â¦": hard.append("BROKEN_SENTENCE")
        words=summary.split()
        if len(words)<45: soft.append("SUMMARY_SHORT")
        if len(words)>100: soft.append("SUMMARY_LONG")
        if len(headline)>100: soft.append("HEADLINE_LONG")
        if len(points)==1: soft.append("ONE_KEY_POINT")
        if not value.get("why_it_matters"): soft.append("WHY_IT_MATTERS_ABSENT")
        normalized=[str(x).strip().casefold() for x in points]
        if len(normalized)!=len(set(normalized)): hard.append("DUPLICATE_KEY_POINTS")
        if summary and len(set(summary.casefold().split()))<max(3,len(summary.split())//3): hard.append("EXTREME_REPETITION")
        if any(str(p).strip().casefold() in headline.casefold() for p in points): soft.append("KEY_POINT_HEADLINE_OVERLAP")
        return {"status":"HARD_REJECT" if hard else "SOFT_WARNING" if soft else "QUALITY_PASS","hard_reasons":hard,"soft_warnings":soft}

class SemanticSummarizerV2(SemanticSummarizer):
    prompt_version="semantic_summarizer_v2"
    class _Validator(SummaryGroundingValidator):
        entity_validator_cls = EntityGroundingValidatorV2
    def __init__(self,service):
        self.service=service; self.validator=self._Validator()

class EditorialRepairPass:
    prompt_version="semantic_summarizer_repair_v1"; schema_version="editorial_summary_v1"
    def __init__(self,service): self.service=service; self.validator=SummaryGroundingValidator()
    def repair(self,event,evidence_pack,original,reasons):
        prompt="REPAIR ONLY EDITORIAL FORM. Rewrite the supplied summary in natural Brazilian Portuguese, preserving every factual detail and number. Do not add facts. Use the same evidence and source_refs. Fix only: "+", ".join(reasons)+". Return the exact structured summary JSON fields from daily_summary_v1. EVIDENCE="+json.dumps(evidence_pack,ensure_ascii=False)+" ORIGINAL="+json.dumps(original,ensure_ascii=False)
        result=self.service.call(event.get("event_id",""),prompt,self.prompt_version,self.schema_version,self.validator.validate,len(event.get("articles",[])),False,event,0.0)
        return {"status":"VALID" if result.get("status") in {"accepted","cache_hit"} and result.get("semantic_status") in {"VALID","REVIEW"} else "INVALID","result":result.get("result"),"validation_status":result.get("semantic_status"),"grounding_errors":result.get("validation_codes",[]),"latency_ms":result.get("latency_ms"),"attempt_count":result.get("attempts",0)}

def run_phase321(evaluation_path=str(ENGINE_OUTPUT / "phase_3_2_evidence_audit.json"),target_count=10):
    from newzi_engine.llm.cache import LLMCache
    from newzi_engine.llm.ollama import OllamaProvider
    from newzi_engine.semantic.service import SemanticService
    data=json.loads(Path(evaluation_path).read_text(encoding="utf-8")); model="llama3.1:8b"; provider=OllamaProvider("http://localhost:11434",model,20,1); service=SemanticService(provider,LLMCache("data/news_engine_phase321.sqlite3"),retries=1); summarizer=SemanticSummarizerV2(service); repair=EditorialRepairPass(service); gate=SummaryQualityGateV2(); audits=[]
    for row in data:
        event=row["input_original"]; event={**event,"articles":[{**a,"description":next((p["evidence_text"] for p in row["evidence_pack"]["articles"] if p["article_id"]==f"article_{i+1:02d}"),a.get("description",""))} for i,a in enumerate(event.get("articles",[]))]}; initial=summarizer.summarize(event,use_cache=False); quality=gate.evaluate(initial); repair_result=None
        if initial.get("status")=="VALID" and quality["status"]=="HARD_REJECT": repair_result=repair.repair(event,row["evidence_pack"],initial.get("result"),quality["hard_reasons"]); post_quality=gate.evaluate(repair_result); final=repair_result if post_quality["status"]!="HARD_REJECT" and repair_result.get("status")=="VALID" else initial; quality=post_quality if final is repair_result else quality
        else: final=initial
        audits.append({"event_id":row["event_id"],"rank_original":row["rank_original"],"evidence_quality":row["evidence_pack"]["event_evidence_quality"],"initial":initial,"initial_quality":gate.evaluate(initial),"repair_attempted":repair_result is not None,"repair":repair_result,"final":final,"final_quality":quality})
    factual_valid=[x for x in audits if x["final"].get("status")=="VALID"]; accepted=[x for x in factual_valid if x["final_quality"]["status"] in {"QUALITY_PASS","SOFT_WARNING"}]; hard=[x for x in factual_valid if x["final_quality"]["status"]=="HARD_REJECT"]; soft=[x for x in factual_valid if x["final_quality"]["status"]=="SOFT_WARNING"]; accepted_errors=[c for x in accepted for c in x["final"].get("grounding_errors",[])]; repair_count=sum(x["repair_attempted"] for x in audits); metrics={"factual_valid_rate":len(factual_valid)/max(1,len(audits)),"hard_quality_reject_rate":len(hard)/max(1,len(factual_valid)),"soft_warning_rate":len(soft)/max(1,len(factual_valid)),"quality_pass_rate":sum(x["final_quality"]["status"]=="QUALITY_PASS" for x in factual_valid)/max(1,len(factual_valid)),"repair_attempt_rate":repair_count/max(1,len(audits)),"repair_success_rate":sum(x["repair_attempted"] and x["final"].get("status")=="VALID" and x["final_quality"]["status"]!="HARD_REJECT" for x in audits)/max(1,repair_count),"final_acceptance_rate":len(accepted)/max(1,len(audits)),"accepted_count":len(accepted),"hard_reject_count":len(hard),"grounding_validity_rate":1.0 if not accepted_errors else 0.0,"number_preservation_rate":1.0 if not any("NUMBER" in c or "DATE" in c for c in accepted_errors) else 0.0,"zero_numeric_hallucinations_accepted":not any("NUMBER" in c or "DATE" in c or "AMOUNT" in c or "PERCENTAGE" in c for c in accepted_errors),"latency_ms":{"p50":statistics.median([x["final"].get("latency_ms",0) or 0 for x in audits]),"max":max([x["final"].get("latency_ms",0) or 0 for x in audits],default=0)}}
    out=Path(str(ENGINE_OUTPUT)); out.mkdir(parents=True,exist_ok=True); (out/"phase_3_2_1_evaluation.json").write_text(json.dumps({"before":{"phase_3_1_factual_valid":"6/10","phase_3_2_factual_valid":"8/10","phase_3_2_briefing_items":3},"metrics":metrics,"audits":audits},ensure_ascii=False,indent=2),encoding="utf-8"); items=[]
    for x in accepted:
        v=x["final"].get("result",{}); items.append({"rank_original":x["rank_original"],"event_id":x["event_id"],"headline":v.get("headline"),"summary":v.get("summary"),"why_it_matters":v.get("why_it_matters"),"key_points":v.get("key_points"),"confidence":v.get("confidence"),"source_refs":v.get("source_refs",[]),"evidence_quality":x["evidence_quality"]})
    briefing={"briefing_id":"briefing_3_2_1","generated_at":datetime.now().isoformat(),"target_count":target_count,"actual_count":len(items),"events_considered":len(audits),"events_rejected":len(audits)-len(items),"items":items}; (out/"daily_briefing_v1_1.json").write_text(json.dumps(briefing,ensure_ascii=False,indent=2),encoding="utf-8"); lines=["SEU BRIEFING DE TECNOLOGIA",datetime.now().strftime("%d de %B de %Y"),""]
    for i,item in enumerate(items,1): lines += [f"{i}. {item['headline']}","",item["summary"],""]+(["Por que importa:",item["why_it_matters"] or ""] if item.get("why_it_matters") else [])+["Pontos principais:"]+[f"Ã¢â‚¬Â¢ {p}" for p in item["key_points"]]+[""]
    (out/"daily_briefing_v1_1.md").write_text("\n".join(lines),encoding="utf-8"); (out/"phase_3_2_1_human_audit.json").write_text(json.dumps([{ "event_id":x["event_id"],"headline":x["final"].get("result",{}).get("headline"),"summary":x["final"].get("result",{}).get("summary"),"factual_accuracy":None,"natural_portuguese":None,"usefulness":None,"headline_quality":None,"why_it_matters_quality":None,"would_read":None,"human_notes":None} for x in accepted],ensure_ascii=False,indent=2),encoding="utf-8"); ready=metrics["factual_valid_rate"]>=.8 and metrics["hard_quality_reject_rate"]<=.1 and metrics["final_acceptance_rate"]>=.8 and metrics["zero_numeric_hallucinations_accepted"]; Path("REPORT_PHASE_3_2_1.md").write_text("# NEWS ENGINE Ã¢â‚¬â€ FASE 3.2.1\n\n"+json.dumps({"PHASE_1":"FROZEN","PHASE_2":"SHADOW / VALIDATION_PENDING","PHASE_3_1":"COMPLETE","PHASE_3_2":"COMPLETE","PHASE_3_2_1":"COMPLETE","metrics":metrics,"READY_FOR_PHASE_3_3":"YES" if ready else "NO","READY_FOR_PRODUCTION":"NO"},ensure_ascii=False,indent=2)+"\n\nHuman audit is mandatory before final promotion.",encoding="utf-8"); return metrics


