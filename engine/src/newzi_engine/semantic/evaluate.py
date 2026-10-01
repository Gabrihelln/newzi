import json, os, statistics, time
from pathlib import Path
from .service import SemanticService, SemanticClassifier, SemanticClusterVerifier
from .schemas import EVENT_TYPES
from newzi_engine.llm.cache import LLMCache
from newzi_engine.llm.ollama import OllamaProvider
from newzi_engine.llm.hardware import detect_hardware
from .gold_v2 import write_gold_v2
from .validator import norm
from .hierarchy import HierarchicalClassifier, family_for_type
from .hybrid import HybridEditorialRouter, EventTypeCandidateGenerator, PairEvidenceComparator
from newzi_engine.paths import ENGINE_DATA, ENGINE_FIXTURES, ENGINE_OUTPUT

def _event(case):
    if case["kind"]=="single": return {"event_id":case["id"],"representative_title":case["title"],"categories":[],"content_genre":"OTHER","fingerprint":{},"articles":[{"article_id":case["id"]+"a","title":case["title"],"description":case.get("description","")[:800],"published_at":"2026-09-15T00:00:00Z","source_type":"JOURNALISM","source_tags":[]}]}
    return {"article_id":case["id"]+"a","title":case["a"]["title"],"description":case["a"].get("description","")[:800],"fingerprint":{}}

def _entity_match(expected,actual):
    if expected is None: return actual is None or not actual
    return bool(actual) and (expected.casefold() in actual.casefold() or actual.casefold() in expected.casefold())

def run_model(model,cases,cache_path=str(ENGINE_DATA / "news_engine.sqlite3"),consistency=False,variant="zero_shot",consistency_count=10,use_cache=False):
    provider=OllamaProvider(os.getenv("OLLAMA_BASE_URL","http://localhost:11434"),model,float(os.getenv("LLM_TIMEOUT_SECONDS","60")),1); health=provider.health_check()
    result={"model":model,"health":health,"single":[],"pairs":[],"consistency":[]}
    if not health.get("available"): return result
    service=SemanticService(provider,LLMCache(cache_path),retries=1); classifier=SemanticClassifier(service,variant=variant); verifier=SemanticClusterVerifier(service)
    singles=[c for c in cases if c["kind"]=="single"]; pairs=[c for c in cases if c["kind"]=="pair"]
    for c in singles:
        out=classifier.classify(_event(c),use_cache=use_cache); result["single"].append({"id":c["id"],"expected":c["expected"],"actual":out})
    for c in pairs:
        out=verifier.verify(_event(c),{**_event(c),**{ "article_id":c["id"]+"b","title":c["b"]["title"],"description":c["b"].get("description","")}},use_cache=use_cache); result["pairs"].append({"id":c["id"],"expected_same":c["expected_same"],"actual":out})
    if consistency:
        for c in singles[:consistency_count]:
            runs=[]
            for n in range(5): runs.append(classifier.classify(_event(c),use_cache=False))
            results=[x.get("result",{}) for x in runs if x.get("status")=="accepted"]; entity_values={norm(x.get("main_entity")) for x in results}; type_values={norm(x.get("event_type")) for x in results}; result["consistency"].append({"id":c["id"],"runs":runs,"entity_stability":(1/len(entity_values) if results else 0),"event_type_stability":(1/len(type_values) if results else 0),"entity_consistency":(1/len(entity_values) if results else 0),"event_type_consistency":(1/len(type_values) if results else 0),"confidence_variance":statistics.pvariance([x.get("confidence",0) for x in results]) if results else None})
    return result

def metrics(result):
    singles=result["single"]; pairs=result["pairs"]; accepted=[x for x in singles if x["actual"].get("status") in {"accepted","cache_hit"}]; valid=len(accepted)/max(1,len(singles)); entity=sum(_entity_match(x["expected"].get("main_entity"),x["actual"]["result"].get("main_entity")) for x in accepted)/max(1,len(accepted)); types=sum(x["expected"].get("event_type")==x["actual"]["result"].get("event_type") for x in accepted)/max(1,len(accepted)); news=sum(x["expected"].get("is_news_event")==x["actual"]["result"].get("is_news_event") for x in accepted)/max(1,len(accepted)); evergreen=sum(x["expected"].get("is_evergreen")==x["actual"]["result"].get("is_evergreen") for x in accepted)/max(1,len(accepted)); pa=[x for x in pairs if x["actual"].get("status") in {"accepted","cache_hit"}]; predicted=[x["actual"]["result"].get("decision")=="SAME_EVENT" for x in pa]; gold=[x["expected_same"] for x in pa]; tp=sum(a and b for a,b in zip(predicted,gold)); fp=sum(a and not b for a,b in zip(predicted,gold)); fn=sum((not a) and b for a,b in zip(predicted,gold)); lat=[x["actual"].get("latency_ms") for x in singles if x["actual"].get("latency_ms")]; toks=[x["actual"].get("output_tokens") for x in singles if x["actual"].get("output_tokens")]; disagreements=[x["id"] for x in accepted if not (_entity_match(x["expected"].get("main_entity"),x["actual"]["result"].get("main_entity")) and x["expected"].get("event_type")==x["actual"]["result"].get("event_type") and x["expected"].get("is_news_event")==x["actual"]["result"].get("is_news_event") and x["expected"].get("is_evergreen")==x["actual"]["result"].get("is_evergreen") )]; high_confidence_errors=[x["id"] for x in accepted if x["actual"]["result"].get("confidence",0)>=.85 and x["id"] in disagreements]; return {"schema_validity":valid,"entity_accuracy":entity,"event_type_accuracy":types,"news_event_accuracy":news,"evergreen_accuracy":evergreen,"same_event_accuracy":sum(a==b for a,b in zip(predicted,gold))/max(1,len(gold)),"same_event_precision":tp/max(1,tp+fp),"same_event_recall":tp/max(1,tp+fn),"accepted_singles":len(accepted),"accepted_pairs":len(pa),"average_latency_ms":statistics.mean(lat) if lat else None,"p95_latency_ms":sorted(lat)[max(0,int(len(lat)*.95)-1)] if lat else None,"average_output_tokens":statistics.mean(toks) if toks else None,"disagreements":disagreements,"high_confidence_errors":high_confidence_errors,"latencies_ms":lat,"output_tokens":toks}

def run_evaluation(models=("llama3.2:3b","llama3.1:8b"),fixture=ENGINE_FIXTURES / "semantic_gold_v1.json"):
    cases=json.loads(Path(fixture).read_text(encoding="utf-8"))["cases"]; all_results=[]
    for model in models: all_results.append(run_model(model,cases,consistency=True))
    report={"dataset":fixture,"hardware":detect_hardware(),"models":[{"model":r["model"],"metrics":metrics(r),"health":r["health"],"consistency":r["consistency"]} for r in all_results],"results":all_results}
    path=Path(str(ENGINE_OUTPUT)); path.mkdir(parents=True,exist_ok=True); (path/"semantic_evaluation.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# Semantic Evaluation 2.2",f"Dataset: {fixture}","", "## Model comparison", "", "| Metric | "+" | ".join(r["model"] for r in report["models"])+" |","|---|"+"---:|"*len(report["models"])]
    keys=["schema_validity","entity_accuracy","event_type_accuracy","news_event_accuracy","evergreen_accuracy","same_event_precision","same_event_recall","same_event_accuracy"]
    for key in keys: lines.append("| "+key+" | "+" | ".join(f"{r['metrics'][key]:.3f}" for r in report["models"])+" |")
    lines += ["", "## Consistency", "", "Consistency runs were executed 5 times for 5 single-event cases without cache."]
    for r in all_results:
        lines.append(f"- {r['model']}: "+"; ".join(f"{x['id']} entity={x['entity_consistency']:.2f}, event_type={x['event_type_consistency']:.2f}, variance={x['confidence_variance']}" for x in r["consistency"]))
    lines += ["", "## Limitations", "", "Metrics are offline gold-set measurements, not a production quality guarantee. Semantic outputs remain shadow-only."]
    (path/"semantic_evaluation.md").write_text("\n".join(lines),encoding="utf-8"); return report

def refresh_evaluation_artifacts():
    path=Path(str(ENGINE_OUTPUT / "semantic_evaluation.json")); report=json.loads(path.read_text(encoding="utf-8"));
    for model, result in zip(report["models"], report["results"]): model["metrics"]=metrics(result)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# Semantic Evaluation 2.2",f"Dataset: {ENGINE_FIXTURES / 'semantic_gold_v1.json'}","", "## Model comparison", "", "| Metric | "+" | ".join(r["model"] for r in report["models"])+" |","|---|"+"---:|"*len(report["models"])]
    keys=["schema_validity","entity_accuracy","event_type_accuracy","news_event_accuracy","evergreen_accuracy","same_event_precision","same_event_recall","same_event_accuracy","average_latency_ms","p95_latency_ms","average_output_tokens"]
    for key in keys: lines.append("| "+key+" | "+" | ".join(f"{r['metrics'][key]:.3f}" if isinstance(r['metrics'].get(key),(int,float)) else "-" for r in report["models"])+" |")
    lines += ["", "## Errors and consistency"]
    for r in report["models"]: lines.append(f"- {r['model']}: disagreements={r['metrics']['disagreements']}; high_confidence_errors={r['metrics']['high_confidence_errors']}")
    lines += ["", "Consistency runs were executed 5 times for 5 single-event cases without cache."]
    for r in report["results"]: lines.append(f"- {r['model']}: "+"; ".join(f"{x['id']} entity={x['entity_consistency']:.2f}, event_type={x['event_type_consistency']:.2f}, variance={x['confidence_variance']}" for x in r["consistency"]))
    lines += ["", "## Limitations", "", "Metrics are offline gold-set measurements, not a production quality guarantee. Semantic outputs remain shadow-only."]
    (path.parent/"semantic_evaluation.md").write_text("\n".join(lines),encoding="utf-8")
    return report

def calibration_metrics(result, cases):
    singles=result["single"]; accepted=[x for x in singles if x["actual"].get("status")=="accepted"]; valid=[x for x in accepted if x["actual"].get("semantic_status")=="VALID"]; abstained=[x for x in accepted if x["actual"].get("semantic_status")=="ABSTAINED"]; expected_by_id={c["id"]:c for c in cases}
    def acc(key): return sum(x["expected"].get(key)==x["actual"].get("result",{}).get(key) for x in valid)/max(1,len(valid))
    high_errors=[x for x in valid if x["actual"].get("result",{}).get("confidence",0)>=.85 and (x["expected"].get("event_type")!=x["actual"].get("result",{}).get("event_type") or not _entity_match(x["expected"].get("main_entity"),x["actual"].get("result",{}).get("main_entity")))]
    pairs=result["pairs"]; pair_valid=[x for x in pairs if x["actual"].get("status")=="accepted"]; pred=[x["actual"].get("result",{}).get("decision")=="SAME_EVENT" for x in pair_valid]; gold=[x["expected_same"] for x in pair_valid]; tp=sum(a and b for a,b in zip(pred,gold)); fp=sum(a and not b for a,b in zip(pred,gold)); fn=sum((not a) and b for a,b in zip(pred,gold)); tn=sum((not a) and (not b) for a,b in zip(pred,gold));
    lat=[x["actual"].get("latency_ms") for x in singles if x["actual"].get("latency_ms")]; by_language={}
    for x in valid:
        language=expected_by_id.get(x["id"],{}).get("language","unknown"); by_language.setdefault(language,[]).append(x)
    language_accuracy={k:{"count":len(v),"event_type_accuracy":sum(a["expected"].get("event_type")==a["actual"].get("result",{}).get("event_type") for a in v)/max(1,len(v)),"entity_accuracy":sum(_entity_match(a["expected"].get("main_entity"),a["actual"].get("result",{}).get("main_entity")) for a in v)/max(1,len(v))} for k,v in by_language.items()}
    return {"schema_validity":len(accepted)/max(1,len(singles)),"semantic_validity":len(valid)/max(1,len(singles)),"main_entity_accuracy":sum(_entity_match(x["expected"].get("main_entity"),x["actual"].get("result",{}).get("main_entity")) for x in valid)/max(1,len(valid)),"event_type_accuracy":acc("event_type"),"news_event_accuracy":acc("is_news_event"),"evergreen_accuracy":acc("is_evergreen"),"analysis_accuracy":acc("is_analysis"),"promotional_accuracy":acc("is_promotional"),"abstention_rate":len(abstained)/max(1,len(singles)),"valid_abstention_rate":len(abstained)/max(1,len(accepted)),"invalid_output_rate":sum(x["actual"].get("status")!="accepted" for x in singles)/max(1,len(singles)),"high_confidence_error_rate":len(high_errors)/max(1,len(valid)),"grounding_violation_rate":sum(bool(x["actual"].get("validation_codes")) for x in valid)/max(1,len(valid)),"reliability_precision":sum(x["actual"].get("reliability_gate") in {"TRUSTED_SHADOW","REVIEW"} and x["id"] not in {h["id"] for h in high_errors} for x in valid)/max(1,len(valid)),"same_event_precision":tp/max(1,tp+fp),"same_event_recall":tp/max(1,tp+fn),"same_event_f1":2*tp/max(1,2*tp+fp+fn),"different_event_accuracy":tn/max(1,tn+fp),"uncertain_rate":sum(x["actual"].get("result",{}).get("decision")=="UNCERTAIN" for x in pair_valid)/max(1,len(pair_valid)),"false_merge_count":fp,"false_split_count":fn,"reliability_gate_false_accept":sum(x["actual"].get("reliability_gate")=="TRUSTED_SHADOW" and x["id"] in {h["id"] for h in high_errors} for x in valid)/max(1,len(valid)),"average_latency_ms":statistics.mean(lat) if lat else None,"p95_latency_ms":sorted(lat)[max(0,int(len(lat)*.95)-1)] if lat else None,"high_confidence_errors":[x["id"] for x in high_errors],"accuracy_by_language":language_accuracy}

def run_calibration(fixture=ENGINE_FIXTURES / "semantic_gold_v2.json"):
    if not Path(fixture).exists(): write_gold_v2(fixture)
    cases=json.loads(Path(fixture).read_text(encoding="utf-8"))["cases"]; variants=[]
    for variant in ("zero_shot","few_shot"):
        result=run_model("llama3.1:8b",cases,consistency=True,variant=variant,consistency_count=10); variants.append({"variant":variant,"result":result,"metrics":calibration_metrics(result,cases)})
    report={"dataset":fixture,"model":"llama3.1:8b","temperature":0.0,"variants":variants,"hardware":detect_hardware()}; path=Path(str(ENGINE_OUTPUT)); path.mkdir(parents=True,exist_ok=True); (path/"semantic_calibration.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# Semantic Calibration 2.2.1",f"Dataset: {fixture}","","Model: llama3.1:8b | temperature: 0.0","","| Metric | zero-shot | few-shot |","|---|---:|---:|"]
    keys=["schema_validity","semantic_validity","main_entity_accuracy","event_type_accuracy","news_event_accuracy","evergreen_accuracy","abstention_rate","high_confidence_error_rate","reliability_gate_false_accept","same_event_precision","same_event_recall","same_event_f1","false_merge_count","false_split_count","average_latency_ms","p95_latency_ms"]
    for key in keys: lines.append("| "+key+" | "+" | ".join(f"{v['metrics'].get(key,0):.3f}" if isinstance(v['metrics'].get(key),(int,float)) else "-" for v in variants)+" |")
    lines += ["", "## Consistency", ""]
    for v in variants: lines.append(f"- {v['variant']}: "+"; ".join(f"{x['id']} entity={x['entity_stability']:.2f}, event_type={x['event_type_stability']:.2f}, variance={x['confidence_variance']}" for x in v['result']['consistency']))
    lines += ["", "## Limitations", "", "Expected values are deterministic/manual fixture values. Semantic results remain shadow-only."]
    (path/"semantic_calibration.md").write_text("\n".join(lines),encoding="utf-8"); return report

def refresh_calibration_artifacts(fixture=ENGINE_FIXTURES / "semantic_gold_v2.json"):
    path=Path(str(ENGINE_OUTPUT / "semantic_calibration.json")); report=json.loads(path.read_text(encoding="utf-8")); cases=json.loads(Path(fixture).read_text(encoding="utf-8"))["cases"]
    for variant in report["variants"]: variant["metrics"]=calibration_metrics(variant["result"],cases)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    md=Path(str(ENGINE_OUTPUT / "semantic_calibration.md")).read_text(encoding="utf-8")
    md += "\n\n## Accuracy by language\n\n"
    for variant in report["variants"]:
        md += f"- {variant['variant']}: "+"; ".join(f"{lang} entity={values['entity_accuracy']:.3f}, event_type={values['event_type_accuracy']:.3f}" for lang,values in sorted(variant["metrics"].get("accuracy_by_language",{}).items()))+"\n"
    md += "\n## Accuracy by editorial event type\n\nThe fixture uses controlled event_type as the deterministic editorial-type grouping; production genre grouping remains a separate F1 field.\n"
    Path(str(ENGINE_OUTPUT / "semantic_calibration.md")).write_text(md,encoding="utf-8"); return report

def audit_gold_v2(cases):
    rows=[]
    for case in cases:
        status="CLEAR"
        if case.get("human_review_required"): status="AMBIGUOUS"
        elif case.get("kind")=="single" and case.get("expected",{}).get("is_news_event") and case.get("expected",{}).get("is_promotional"): status="QUESTIONABLE"
        rows.append((case["id"],status))
    return rows

def classification_metrics(result,cases):
    singles=result["single"]; rows=[x for x in singles if x["actual"].get("status") in {"accepted","cache_hit"} and x["actual"].get("semantic_status","VALID") in {"VALID","ABSTAINED"}]; labels=sorted({c.get("expected",{}).get("event_type") for c in cases if c.get("kind")=="single"})
    matrix={expected:{pred:0 for pred in labels+['ABSTAIN']} for expected in labels};
    for row in singles:
        expected=row["expected"].get("event_type"); actual=row["actual"].get("result",{}).get("event_type") if row["actual"].get("status") in {"accepted","cache_hit"} else "ABSTAIN"; matrix.setdefault(expected,{})[actual]=matrix.setdefault(expected,{}).get(actual,0)+1
    per_type={}
    for label in labels:
        tp=matrix.get(label,{}).get(label,0); fp=sum(matrix.get(other,{}).get(label,0) for other in labels if other!=label); fn=sum(v for k,v in matrix.get(label,{}).items() if k!=label); per_type[label]={"support":sum(matrix.get(label,{}).values()),"precision":tp/max(1,tp+fp),"recall":tp/max(1,tp+fn),"f1":2*tp/max(1,2*tp+fp+fn)}
    macro={key:sum(v[key] for v in per_type.values())/max(1,len(per_type)) for key in ("precision","recall","f1")}
    trusted=[x for x in rows if x["actual"].get("reliability_gate")=="TRUSTED_SHADOW"]; correct=[x for x in trusted if x["expected"].get("event_type")==x["actual"].get("result",{}).get("event_type")]; families={"NEWS","EDITORIAL","UTILITY","COMMERCIAL","UNKNOWN"}; family_matrix={f:{g:0 for g in families} for f in families}
    for x in rows:
        ef=family_for_type(x["expected"].get("event_type")); af=x["actual"].get("result",{}).get("content_family") or family_for_type(x["actual"].get("result",{}).get("event_type")); family_matrix[ef][af]=family_matrix[ef].get(af,0)+1
    cluster=metrics(result)
    return {"event_type_confusion_matrix":matrix,"event_type_per_type":per_type,"event_type_macro_precision":macro["precision"],"event_type_macro_recall":macro["recall"],"event_type_macro_f1":macro["f1"],"family_confusion_matrix":family_matrix,"semantic_validity":len(rows)/max(1,len(singles)),"trusted_coverage":len(trusted)/max(1,len(singles)),"trusted_precision":len(correct)/max(1,len(trusted)),"classified_rate":sum(x["actual"].get("result",{}).get("decision")=="CLASSIFIED" for x in rows)/max(1,len(singles)),"abstention_rate":sum(x["actual"].get("semantic_status")=="ABSTAINED" for x in singles)/max(1,len(singles)),"review_rate":sum(x["actual"].get("reliability_gate")=="REVIEW" for x in rows)/max(1,len(singles)),"trusted_rate":len(trusted)/max(1,len(singles)),"reject_rate":sum(x["actual"].get("status") not in {"accepted","cache_hit"} for x in singles)/max(1,len(singles)),"same_event_precision":cluster["same_event_precision"],"same_event_recall":cluster["same_event_recall"],"false_merge_count":sum(x["actual"].get("result",{}).get("decision")=="SAME_EVENT" and not x["expected_same"] for x in result["pairs"] if x["actual"].get("status") in {"accepted","cache_hit"}),"false_split_count":sum(x["actual"].get("result",{}).get("decision")!="SAME_EVENT" and x["expected_same"] for x in result["pairs"] if x["actual"].get("status") in {"accepted","cache_hit"})}

def run_hierarchical_evaluation(fixture=ENGINE_FIXTURES / "semantic_gold_v2.json"):
    cases=json.loads(Path(fixture).read_text(encoding="utf-8"))["cases"]
    provider=OllamaProvider(os.getenv("OLLAMA_BASE_URL","http://localhost:11434"),"llama3.1:8b",float(os.getenv("LLM_TIMEOUT_SECONDS","60")),1); health=provider.health_check(); service=SemanticService(provider,LLMCache(str(ENGINE_DATA / "news_engine.sqlite3")),retries=1); classifier=HierarchicalClassifier(service); result={"model":"llama3.1:8b","health":health,"single":[],"pairs":[],"consistency":[]}
    for case in [c for c in cases if c["kind"]=="single"]: result["single"].append({"id":case["id"],"expected":case["expected"],"actual":classifier.classify(_event(case),use_cache=False)})
    # Verifier metrics remain a separate conservative component; use the existing verifier without cache.
    verifier=SemanticClusterVerifier(service)
    for case in [c for c in cases if c["kind"]=="pair"]: result["pairs"].append({"id":case["id"],"expected_same":case["expected_same"],"actual":verifier.verify(_event(case),{**_event(case),"article_id":case["id"]+"b","title":case["b"]["title"],"description":case["b"].get("description","")},use_cache=False)})
    for case in [c for c in cases if c["kind"]=="single"][:10]:
        runs=[classifier.classify(_event(case),use_cache=False) for _ in range(5)]; values=[x.get("result",{}) for x in runs if x.get("status")=="accepted"]; entities={norm(x.get("main_entity")) for x in values}; types={norm(x.get("event_type")) for x in values}; result["consistency"].append({"id":case["id"],"runs":runs,"entity_stability":1/len(entities) if entities else 0,"event_type_stability":1/len(types) if types else 0,"confidence_variance":statistics.pvariance([x.get("confidence",0) for x in values]) if values else None})
    return result

def run_phase_222(fixture=ENGINE_FIXTURES / "semantic_gold_v2.json"):
    cases=json.loads(Path(fixture).read_text(encoding="utf-8"))["cases"]; audit=audit_gold_v2(cases); Path(str(ENGINE_OUTPUT / "gold_v2_audit.md")).write_text("# Gold V2 Audit\n\n"+"\n".join(f"- {i}: {s}" for i,s in audit),encoding="utf-8")
    baseline=run_model("llama3.1:8b",cases,consistency=True,use_cache=False); hierarchical=run_hierarchical_evaluation(fixture); bm=classification_metrics(baseline,cases); hm=classification_metrics(hierarchical,cases); Path(str(ENGINE_OUTPUT / "event_type_confusion_matrix.json")).write_text(json.dumps({"baseline":bm["event_type_confusion_matrix"],"hierarchical":hm["event_type_confusion_matrix"],"family_baseline":bm["family_confusion_matrix"],"family_hierarchical":hm["family_confusion_matrix"]},ensure_ascii=False,indent=2),encoding="utf-8")
    report={"fixture":fixture,"model":"llama3.1:8b","temperature":0.0,"cache":False,"gold_audit_counts":{s:sum(x[1]==s for x in audit) for s in {"CLEAR","AMBIGUOUS","QUESTIONABLE"}},"baseline":{"result":baseline,"metrics":bm},"hierarchical":{"result":hierarchical,"metrics":hm}}
    Path(str(ENGINE_OUTPUT / "hierarchical_semantic_evaluation.json")).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8"); lines=["# Hierarchical Semantic Evaluation 2.2.2","","| Metric | classifier_v3 | hierarchical_classifier_v1 |","|---|---:|---:|"]
    for k in ("semantic_validity","event_type_macro_f1","event_type_macro_precision","event_type_macro_recall","trusted_coverage","trusted_precision","classified_rate","abstention_rate","review_rate","trusted_rate","reject_rate"): lines.append(f"| {k} | {bm.get(k,0):.3f} | {hm.get(k,0):.3f} |")
    lines += ["","## Per-type hierarchical metrics",""]+[f"- {k}: support={v['support']}, precision={v['precision']:.3f}, recall={v['recall']:.3f}, F1={v['f1']:.3f}" for k,v in hm["event_type_per_type"].items()]
    lines += ["","## Gold audit",f"- CLEAR: {report['gold_audit_counts']['CLEAR']}",f"- AMBIGUOUS: {report['gold_audit_counts']['AMBIGUOUS']}",f"- QUESTIONABLE: {report['gold_audit_counts']['QUESTIONABLE']}","","Official metrics use the original Gold V2 expected values; no expected outputs enter prompts."]
    Path(str(ENGINE_OUTPUT / "hierarchical_semantic_evaluation.md")).write_text("\n".join(lines),encoding="utf-8"); return report

def rerun_hierarchical_only(fixture=ENGINE_FIXTURES / "semantic_gold_v2.json"):
    cases=json.loads(Path(fixture).read_text(encoding="utf-8"))["cases"]; path=Path(str(ENGINE_OUTPUT / "hierarchical_semantic_evaluation.json")); report=json.loads(path.read_text(encoding="utf-8")); hierarchical=run_hierarchical_evaluation(fixture); hm=classification_metrics(hierarchical,cases); report["hierarchical"]={"result":hierarchical,"metrics":hm}; path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8"); Path(str(ENGINE_OUTPUT / "event_type_confusion_matrix.json")).write_text(json.dumps({"baseline":report["baseline"]["metrics"]["event_type_confusion_matrix"],"hierarchical":hm["event_type_confusion_matrix"],"family_baseline":report["baseline"]["metrics"]["family_confusion_matrix"],"family_hierarchical":hm["family_confusion_matrix"]},ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# Hierarchical Semantic Evaluation 2.2.2","","| Metric | classifier_v3 | hierarchical_classifier_v1 |","|---|---:|---:|"]
    bm=report["baseline"]["metrics"]
    for k in ("semantic_validity","event_type_macro_f1","event_type_macro_precision","event_type_macro_recall","trusted_coverage","trusted_precision","classified_rate","abstention_rate","review_rate","trusted_rate","reject_rate"): lines.append(f"| {k} | {bm.get(k,0):.3f} | {hm.get(k,0):.3f} |")
    lines += ["","## Per-type hierarchical metrics",""]+[f"- {k}: support={v['support']}, precision={v['precision']:.3f}, recall={v['recall']:.3f}, F1={v['f1']:.3f}" for k,v in hm["event_type_per_type"].items()]; Path(str(ENGINE_OUTPUT / "hierarchical_semantic_evaluation.md")).write_text("\n".join(lines),encoding="utf-8"); return report

def refresh_phase_222_artifacts():
    path=Path(str(ENGINE_OUTPUT / "hierarchical_semantic_evaluation.json")); report=json.loads(path.read_text(encoding="utf-8")); cases=json.loads(Path(report["fixture"]).read_text(encoding="utf-8"))["cases"]; report["baseline"]["metrics"]=classification_metrics(report["baseline"]["result"],cases); report["hierarchical"]["metrics"]=classification_metrics(report["hierarchical"]["result"],cases); path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8"); Path(str(ENGINE_OUTPUT / "event_type_confusion_matrix.json")).write_text(json.dumps({"baseline":report["baseline"]["metrics"]["event_type_confusion_matrix"],"hierarchical":report["hierarchical"]["metrics"]["event_type_confusion_matrix"],"family_baseline":report["baseline"]["metrics"]["family_confusion_matrix"],"family_hierarchical":report["hierarchical"]["metrics"]["family_confusion_matrix"]},ensure_ascii=False,indent=2),encoding="utf-8"); return report

def _f1_metrics(expected, predicted, labels):
    matrix={e:{p:0 for p in labels+['ABSTAIN']} for e in labels}
    for e,p in zip(expected,predicted): matrix.setdefault(e,{})[p]=matrix.setdefault(e,{}).get(p,0)+1
    per={}
    for label in labels:
        tp=matrix.get(label,{}).get(label,0); fp=sum(matrix.get(e,{}).get(label,0) for e in labels if e!=label); fn=sum(v for k,v in matrix.get(label,{}).items() if k!=label)
        per[label]={"support":sum(matrix.get(label,{}).values()),"precision":tp/max(1,tp+fp),"recall":tp/max(1,tp+fn),"f1":2*tp/max(1,2*tp+fp+fn)}
    return matrix,per,{k:sum(v[k] for v in per.values())/max(1,len(per)) for k in ('precision','recall','f1')}

def run_candidate_evaluation(fixture=ENGINE_FIXTURES / "semantic_gold_v2.json"):
    cases=json.loads(Path(fixture).read_text(encoding="utf-8"))["cases"]; singles=[c for c in cases if c["kind"]=="single"]; generator=EventTypeCandidateGenerator(); rows=[]
    for case in singles:
        candidates=generator.generate(_event(case)); target=case["expected"].get("event_type"); types=[x["type"] for x in candidates]
        rows.append({"id":case["id"],"expected":target,"candidates":candidates,"recall_at_1":target in types[:1],"recall_at_2":target in types[:2],"recall_at_3":target in types[:3]})
    strong=[r for r in rows if r["candidates"] and r["candidates"][0]["score"]>=.84 and (len(r["candidates"])==1 or r["candidates"][1]["score"]<.72)]
    metrics={"count":len(rows),"candidate_recall_at_1":sum(r["recall_at_1"] for r in rows)/max(1,len(rows)),"candidate_recall_at_2":sum(r["recall_at_2"] for r in rows)/max(1,len(rows)),"candidate_recall_at_3":sum(r["recall_at_3"] for r in rows)/max(1,len(rows)),"average_candidates":sum(len(r["candidates"]) for r in rows)/max(1,len(rows)),"deterministic_coverage":len(strong)/max(1,len(rows)),"deterministic_precision":sum(r["expected"]==r["candidates"][0]["type"] for r in strong)/max(1,len(strong))}
    report={"fixture":fixture,"generator":"event_type_candidate_generator_v1","metrics":metrics,"rows":rows}; out=Path(str(ENGINE_OUTPUT)); out.mkdir(parents=True,exist_ok=True); (out/"candidate_generator_evaluation.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8"); return report

def _hybrid_metrics(rows):
    labels=sorted({r["expected"] for r in rows}); pred=[r["actual"].get("final_event_type") or "ABSTAIN" for r in rows]; expected=[r["expected"] for r in rows]; matrix,per,macro=_f1_metrics(expected,pred,labels); valid=[r for r in rows if r["actual"].get("output_validity")=="VALID"]; classified=[r for r in valid if r["actual"].get("classification_decision")=="CLASSIFIED"]; trusted=[r for r in classified if r["actual"].get("confidence_state")=="TRUSTED"]; llm=[r for r in rows if r["actual"].get("llm_used")]; llm_classified=[r for r in llm if r["actual"].get("llm_result",{}).get("result",{}).get("decision")=="CLASSIFIED"]
    return {"count":len(rows),"output_validity":len(valid)/max(1,len(rows)),"invalid_rate":1-len(valid)/max(1,len(rows)),"event_type_accuracy":sum(a==b for a,b in zip(expected,pred))/max(1,len(rows)),"classified_rate":len(classified)/max(1,len(rows)),"abstention_rate":sum(r["actual"].get("classification_decision")=="ABSTAIN" for r in rows)/max(1,len(rows)),"trusted_coverage":len(trusted)/max(1,len(rows)),"trusted_precision":sum(r["expected"]==r["actual"].get("final_event_type") for r in trusted)/max(1,len(trusted)),"event_type_macro_precision":macro["precision"],"event_type_macro_recall":macro["recall"],"event_type_macro_f1":macro["f1"],"confusion_matrix":matrix,"per_type":per,"llm_invocation_rate":len(llm)/max(1,len(rows)),"llm_disambiguation_accuracy":sum(r["expected"]==r["actual"].get("final_event_type") for r in llm_classified)/max(1,len(llm_classified)),"llm_disambiguation_abstention_rate":sum(r["actual"].get("llm_result",{}).get("result",{}).get("decision")=="ABSTAIN" for r in llm)/max(1,len(llm)),"decision_sources":{s:sum(r["actual"].get("decision_source")==s for r in rows) for s in ("DETERMINISTIC","LLM_DISAMBIGUATION","ABSTAIN")}}

def run_hybrid_evaluation(fixture=ENGINE_FIXTURES / "semantic_gold_v2.json"):
    cases=json.loads(Path(fixture).read_text(encoding="utf-8"))["cases"]; provider=OllamaProvider(os.getenv("OLLAMA_BASE_URL","http://localhost:11434"),"llama3.1:8b",float(os.getenv("LLM_TIMEOUT_SECONDS","60")),1); health=provider.health_check(); service=SemanticService(provider,LLMCache("data/news_engine_hybrid.sqlite3"),retries=1); router=HybridEditorialRouter(service); rows=[]
    for case in [c for c in cases if c["kind"]=="single"]:
        actual=router.route(_event(case),use_cache=False); rows.append({"id":case["id"],"expected":case["expected"].get("event_type"),"actual":actual})
    metrics_out=_hybrid_metrics(rows); report={"fixture":fixture,"model":"llama3.1:8b","temperature":0.0,"cache":False,"health":health,"metrics":metrics_out,"rows":rows}; out=Path(str(ENGINE_OUTPUT)); out.mkdir(parents=True,exist_ok=True); (out/"hybrid_router_evaluation.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    errors=[]
    for r in rows:
        if r["expected"]!=r["actual"].get("final_event_type"):
            errors.append({"id":r["id"],"expected":r["expected"],"candidates":r["actual"].get("candidate_scores",[]),"final":r["actual"].get("final_event_type"),"decision_source":r["actual"].get("decision_source"),"category":"OUTPUT_INVALID" if r["actual"].get("output_validity")!="VALID" else ("CANDIDATE_MISS" if r["expected"] not in r["actual"].get("candidate_types",[]) else ("UNNECESSARY_ABSTAIN" if r["actual"].get("classification_decision")=="ABSTAIN" else "LLM_DISAMBIGUATION_ERROR"))})
    (out/"hybrid_error_analysis.json").write_text(json.dumps({"errors":errors,"count":len(errors)},ensure_ascii=False,indent=2),encoding="utf-8"); lines=["# Hybrid Router Evaluation 2.2.3","",f"Model: llama3.1:8b | temperature: 0.0 | cache: false","", "| Metric | Value |","|---|---:|"]+[f"| {k} | {v:.3f} |" if isinstance(v,float) else f"| {k} | {v} |" for k,v in metrics_out.items() if not isinstance(v,(dict,list))]; (out/"hybrid_router_evaluation.md").write_text("\n".join(lines),encoding="utf-8"); return report

def run_verifier_false_split_analysis(fixture=ENGINE_FIXTURES / "semantic_gold_v2.json"):
    path=Path(str(ENGINE_OUTPUT / "hierarchical_semantic_evaluation.json")); report=json.loads(path.read_text(encoding="utf-8")); cases=json.loads(Path(fixture).read_text(encoding="utf-8"))["cases"]; pairs=report["hierarchical"]["result"].get("pairs",[]); by_id={c["id"]:c for c in cases}; comparator=PairEvidenceComparator(); rows=[]
    for r in pairs:
        if r["expected_same"] and r["actual"].get("result",{}).get("decision")!="SAME_EVENT":
            c=by_id[r["id"]]; rows.append({"id":r["id"],"expected_same":True,"predicted":r["actual"].get("result",{}).get("decision"),"comparison":comparator.compare(c["a"],c["b"]),"safe_recovery":False,"note":"Comparator is diagnostic only; no automatic merge applied."})
    out=Path(str(ENGINE_OUTPUT / "verifier_false_split_analysis.json")); out.write_text(json.dumps({"source":"hierarchical_semantic_evaluation.json","false_splits":rows,"count":len(rows),"false_merge_count":report["hierarchical"]["metrics"].get("false_merge_count",0)},ensure_ascii=False,indent=2),encoding="utf-8"); return {"false_split_count":len(rows),"false_merge_count":report["hierarchical"]["metrics"].get("false_merge_count",0)}


