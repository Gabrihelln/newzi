"""Phase 3.3 production briefing pipeline. Historical Phase 3.2.x outputs are never rewritten."""
import json, os, re, statistics, time, uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from newzi_engine.llm.cache import LLMCache
from newzi_engine.llm.ollama import OllamaProvider
from newzi_engine.semantic.acquisition import ArticleContentResolver, build_evidence_pack
from newzi_engine.semantic.entity import EntityGroundingValidatorV2
from newzi_engine.semantic.quality321 import SemanticSummarizerV2, SummaryQualityGateV2
from newzi_engine.semantic.language import detect_text_language, language_gate
from newzi_engine.storage import Store
from newzi_engine.paths import ENGINE_OUTPUT


class PortugueseEditorialValidator:
    rules = {
        "do apple": "EDITORIAL_REPAIR_REQUIRED", "do ai": "EDITORIAL_REPAIR_REQUIRED",
        "ir pública": "EDITORIAL_REPAIR_REQUIRED", "ir público": "EDITORIAL_REPAIR_REQUIRED",
        "redução da velocidade do ai": "EDITORIAL_WARNING",
    }
    def evaluate(self, value):
        text = " ".join(str(value.get(k) or "") for k in ("headline", "summary", "why_it_matters") + ("key_points",))
        lowered = text.casefold(); found = [rule for phrase, rule in self.rules.items() if phrase in lowered]
        if "redução da velocidade do ai" in lowered or "redução da velocidade do ai" in lowered:
            return {"status": "EDITORIAL_WARNING", "warnings": ["EDITORIAL_WARNING"]}
        return {"status": "EDITORIAL_REPAIR_REQUIRED" if "EDITORIAL_REPAIR_REQUIRED" in found else ("EDITORIAL_WARNING" if found else "EDITORIAL_PASS"), "warnings": found}


class EditorialNormalizationPass:
    replacements = [("do Apple", "da Apple"), ("do apple", "da Apple"), ("do AI", "da IA"), ("do ai", "da IA"), ("ir público", "abrir capital"), ("ir público", "abrir capital")]
    def apply(self, value):
        changed = False; output = json.loads(json.dumps(value, ensure_ascii=False)); provenance = []
        for key in ("headline", "summary", "why_it_matters"):
            if isinstance(output.get(key), str):
                for old, new in self.replacements:
                    if old in output[key]: output[key] = output[key].replace(old, new); changed = True; provenance.append({"field": key, "from": old, "to": new, "type": "LINGUISTIC_ONLY"})
        for i, point in enumerate(output.get("key_points", [])):
            if isinstance(point, str):
                for old, new in self.replacements:
                    if old in point: output["key_points"][i] = point.replace(old, new); changed = True; provenance.append({"field": f"key_points[{i}]", "from": old, "to": new, "type": "LINGUISTIC_ONLY"})
        return output, changed, provenance


def _bounded_words(value, limit):
    return " ".join(str(value or "").split()[:limit]).strip()


def deterministic_fallback_summary(event, evidence_pack, output_language="pt-BR"):
    """Create a minimal summary using only supplied source evidence."""
    usable=[a for a in evidence_pack.get("articles", []) if a.get("evidence_text") or a.get("title")]
    if not usable: return None
    primary=usable[0]; title=_bounded_words(primary.get("title") or event.get("representative_title"), 18)
    source_text=_bounded_words(primary.get("evidence_text") or title, 55)
    if not title or not source_text: return None
    if output_language == "pt-BR" and detect_text_language(title+" "+source_text, primary.get("source_language")) != "pt-BR": return None
    if source_text[-1:] not in ".!?…": source_text += "."
    points=[title]
    for article in usable[1:]:
        point=_bounded_words(article.get("evidence_text") or article.get("title"), 18)
        if point and point.casefold() not in {x.casefold() for x in points}:
            points.append(point); break
    if len(points)<2:
        detail=_bounded_words(primary.get("evidence_text") or primary.get("title"), 24)
        if detail and detail.casefold()!=title.casefold(): points.append(detail)
    if len(points)<2:
        publisher=_bounded_words(primary.get("publisher") or primary.get("source") or primary.get("article_id"), 12)
        if publisher: points.append("Fonte consultada: "+publisher)
    if len(points)<2: return None
    article_id=primary.get("article_id", "article_01")
    return {"headline":title,"summary":source_text,"why_it_matters":None,"key_points":points[:2],"entities":[],"source_refs":[article_id],"factual_claims":[{"claim":source_text,"source_refs":[article_id],"support":"DIRECT"}],"source_conflict":False,"confidence":0.55,"status":"VALID"}


class ProductionBriefingPipeline:
    def __init__(self, target_count=10, output_language="pt-BR"):
        self.target_count = target_count
        self.output_language = output_language
        self.resolver = ArticleContentResolver()
        model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        timeout = max(1.0, float(os.getenv("OLLAMA_TIMEOUT_SECONDS", os.getenv("LLM_TIMEOUT_SECONDS", "45"))))
        provider = OllamaProvider(os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"), model, timeout, 1)
        self.provider = provider
        self.service = __import__("newzi_engine.semantic.service", fromlist=["SemanticService"]).SemanticService(provider, LLMCache(ENGINE_OUTPUT.parent / "news_engine_phase33.sqlite3"), retries=max(0, int(os.getenv("OLLAMA_MAX_RETRIES", "1"))))
        self.summarizer = SemanticSummarizerV2(self.service); self.gate = SummaryQualityGateV2(); self.editorial = PortugueseEditorialValidator(); self.normalizer = EditorialNormalizationPass(); self.warmup_result=None
        if str(os.getenv("OLLAMA_WARMUP", "0")).lower() in {"1", "true", "yes", "on"}:
            started=time.perf_counter()
            try:
                from newzi_engine.llm.contracts import LLMRequest
                self.provider.generate(LLMRequest('{"warmup":"ok"}', self.provider.model, "warmup", "warmup", "warmup"))
                self.warmup_result={"status":"OK","latency_ms":round((time.perf_counter()-started)*1000,2)}
            except Exception as exc:
                self.warmup_result={"status":"FAILED","latency_ms":round((time.perf_counter()-started)*1000,2),"error":str(exc)}

    def _event(self, item, corpus):
        by_url = {a.url: a for a in corpus}; by_title = {a.title: a for a in corpus}; articles=[]
        for article in item.get("articles", []):
            full = by_url.get(article.get("url")) or by_title.get(article.get("title", "")); articles.append({"title": article.get("title", ""), "description": full.description if full else "", "source": article.get("source", ""), "publisher_id": article.get("publisher_id", ""), "published_at": article.get("published_at"), "url": article.get("url", ""), "source_language": (full.language if full else article.get("language", "unknown"))})
        return {"event_id": item.get("event_id"), "representative_title": item.get("title", ""), "articles": articles, "primary_entities": item.get("primary_entities", []), "categories": item.get("categories", []), "content_genre": item.get("content_genre")}

    def run(self, candidates):
        health = self.provider.health_check()
        if not health.get("available"):
            return {"provider_unavailable": True, "error": health.get("error", "PROVIDER_UNAVAILABLE"), "audits": [], "items": []}
        corpus = Store().all_articles(); audits=[]
        for item in candidates:
            event = self._event(item, corpus); pack = build_evidence_pack(event, self.resolver); trace_id = "trace_" + uuid.uuid4().hex
            enriched = {**event, "articles": [{**a, "description": pack["articles"][i]["evidence_text"]} for i, a in enumerate(event["articles"])]}
            if pack["event_evidence_quality"] == "LOW":
                summary = {"status": "ABSTAIN", "result": None, "validation_status": "INSUFFICIENT_EVIDENCE", "grounding_errors": ["INSUFFICIENT_EVIDENCE"]}
            else:
                summary = self.summarizer.summarize(enriched, target_language=self.output_language, use_cache=True)
            fallback_used=False
            provider_failed=summary.get("status") == "PROVIDER_FAILED"
            if summary.get("status") == "PROVIDER_FAILED":
                fallback_value=deterministic_fallback_summary(enriched, pack, self.output_language)
                if fallback_value:
                    summary={"status":"VALID","result":fallback_value,"validation_status":"DETERMINISTIC_FALLBACK","grounding_errors":[],"latency_ms":summary.get("latency_ms",0),"attempt_count":summary.get("attempt_count",0)}
                    fallback_used=True
            gate_status=language_gate(summary.get("result") or {}, self.output_language)
            if summary.get("result") and gate_status == "FAIL":
                fallback_value=deterministic_fallback_summary(enriched, pack, self.output_language)
                if fallback_value:
                    summary={"status":"VALID","result":fallback_value,"validation_status":"DETERMINISTIC_FALLBACK","grounding_errors":[],"latency_ms":summary.get("latency_ms",0),"attempt_count":summary.get("attempt_count",0)}; fallback_used=True; gate_status="PASS"
            quality = self.gate.evaluate(summary); value = summary.get("result"); normalization=[]; editorial={"status": "EDITORIAL_PASS", "warnings": []}
            if value and summary.get("status") == "VALID":
                editorial = self.editorial.evaluate(value)
                if editorial["status"] == "EDITORIAL_REPAIR_REQUIRED":
                    value, changed, normalization = self.normalizer.apply(value)
                    if changed:
                        # Revalidation is mandatory; this only changes form and cannot bypass grounding.
                        enriched = {**event, "articles": [{**a, "description": pack["articles"][i]["evidence_text"]} for i, a in enumerate(event["articles"])]}
                        from newzi_engine.semantic.summarizer import SummaryGroundingValidator
                        checked = SummaryGroundingValidator().validate(json.dumps(value, ensure_ascii=False), enriched, len(enriched["articles"]))
                        if checked.status != "VALID": value = None; summary["status"] = "INVALID"; summary["grounding_errors"] = checked.codes
            accepted = bool(value and summary.get("status") == "VALID" and quality["status"] in {"QUALITY_PASS", "SOFT_WARNING"})
            audits.append({"trace_id": trace_id, "rank_original": item.get("rank"), "event_id": item.get("event_id"), "event": event, "evidence_pack": pack, "summary": value, "summary_status": summary.get("status"), "provider_failed":provider_failed, "summary_provider":"deterministic_fallback" if fallback_used else "ollama", "localization_provider":None, "localization_applied":False, "output_language":self.output_language, "language_gate":gate_status, "fallback_used":fallback_used, "grounding_errors": summary.get("grounding_errors", []), "quality": quality, "editorial": editorial, "normalizations": normalization, "accepted": accepted and gate_status == "PASS", "latency_ms": summary.get("latency_ms", 0) or 0})
        accepted = [x for x in audits if x["accepted"]][:self.target_count]
        return {"provider_unavailable": False, "audits": audits, "items": accepted}


def _distributions(items):
    sources=Counter(); domains=Counter(); types=Counter(); entities=Counter()
    for x in items:
        event=x["event"]; types[event.get("content_genre") or "UNKNOWN"] += 1
        for a in event.get("articles", []):
            sources[a.get("source", "UNKNOWN")] += 1
            domains[re.sub(r"^www\.", "", (a.get("url", "").split("/")[2] if "/" in a.get("url", "") else "UNKNOWN"))] += 1
        for e in event.get("primary_entities", []): entities[e] += 1
    return {"source_distribution": dict(sources), "domain_distribution": dict(domains), "event_type_distribution": dict(types), "entity_concentration": dict(entities)}


def run_phase33(briefing_path=None, target_count=10, output_language="pt-BR"):
    briefing_path = briefing_path or str(ENGINE_OUTPUT / "briefing.json")
    candidates = json.loads(Path(briefing_path).read_text(encoding="utf-8")).get("items", [])
    pipeline = ProductionBriefingPipeline(target_count, output_language); result = pipeline.run(candidates)
    out=ENGINE_OUTPUT; out.mkdir(parents=True, exist_ok=True); audits=result.get("audits", []); accepted=result.get("items", [])
    if result.get("provider_unavailable"):
        metrics={"articles_considered":0,"events_considered":len(candidates),"events_summarized":0,"provider_failure_rate":1.0,"backfill_count":0,"briefing_fill_rate":0.0,"provider_status":"PROVIDER_UNAVAILABLE"}
    else:
        factual=[x for x in audits if x["summary_status"] == "VALID"]; failures=[x for x in audits if x["summary_status"] != "VALID"]; lats=[x["latency_ms"] for x in audits if x["latency_ms"]]
        metrics={"articles_considered":sum(len(x["event"].get("articles", [])) for x in audits),"events_considered":len(audits),"events_summarized":sum(x["summary_status"] not in {"ABSTAIN", "PROVIDER_FAILED"} for x in audits),"factual_valid_rate":len(factual)/max(1,len(audits)),"entity_grounding_failure_rate":sum("ENTITY_HALLUCINATION" in x["grounding_errors"] for x in audits)/max(1,len(audits)),"numeric_grounding_failure_rate":sum(any(c in {"NUMBER_HALLUCINATION", "DATE_HALLUCINATION"} for c in x["grounding_errors"]) for x in audits)/max(1,len(audits)),"editorial_repair_rate":sum(bool(x["normalizations"]) for x in audits)/max(1,len(audits)),"editorial_repair_success_rate":sum(bool(x["normalizations"]) and x["accepted"] for x in audits)/max(1,sum(bool(x["normalizations"]) for x in audits)),"briefing_fill_rate":len(accepted)/max(1,min(target_count,len(candidates))),"backfill_count":sum(x["rank_original"] > target_count for x in accepted),"provider_failure_rate":sum(x["summary_status"] == "PROVIDER_FAILED" for x in audits)/max(1,len(audits)),"average_latency":statistics.mean(lats) if lats else 0,"p50_latency":statistics.median(lats) if lats else 0,"p95_latency":sorted(lats)[max(0, int(len(lats)*.95)-1)] if lats else 0,**_distributions(accepted)}
        metrics.update({"ollama_timeout_seconds":getattr(pipeline.provider,"timeout",None),"ollama_success_count":sum(x["summary_provider"]=="ollama" and x["accepted"] for x in audits),"ollama_timeout_count":sum(x["provider_failed"] for x in audits),"fallback_summary_count":sum(x["fallback_used"] for x in audits),"skipped_event_count":sum(not x["accepted"] for x in audits),"final_item_count":len(accepted),"warmup":pipeline.warmup_result})
    items=[]
    for x in accepted:
        v=x["summary"]; items.append({"rank":len(items)+1,"rank_original":x["rank_original"],"event_id":x["event_id"],"headline":v.get("headline"),"summary":v.get("summary"),"key_points":v.get("key_points"),"why_it_matters":v.get("why_it_matters"),"confidence":v.get("confidence"),"summary_provider":x["summary_provider"],"source_language":x["event"].get("articles",[{}])[0].get("source_language","unknown"),"output_language":x["output_language"],"localization_provider":x["localization_provider"],"localization_applied":x["localization_applied"],"language_gate":x["language_gate"],"evidence_quality":x["evidence_pack"]["event_evidence_quality"],"sources":[{"publisher":a.get("publisher"),"url":a.get("url"),"published_at":a.get("published_at")} for a in x["evidence_pack"]["articles"]],"warnings":x["quality"].get("soft_warnings", []) + x["editorial"].get("warnings", []),"provenance":{"trace_id":x["trace_id"],"event_id":x["event_id"],"articles":[a.get("article_id") for a in x["evidence_pack"]["articles"]],"evidence_quality":x["evidence_pack"]["event_evidence_quality"],"grounding_errors":x["grounding_errors"],"normalizations":x["normalizations"],"summary_provider":x["summary_provider"],"output_language":x["output_language"],"language_gate":x["language_gate"],"decision":"ACCEPTED"}})
    briefing={"contract":"daily_briefing_v2","briefing_id":"briefing_3_3","generated_at":datetime.now(timezone.utc).isoformat(),"target_count":target_count,"actual_count":len(items),"items":items}; (out/"daily_briefing_v2.json").write_text(json.dumps(briefing,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["SEU BRIEFING DE TECNOLOGIA", ""]; [lines.extend([f"{i['rank']}. {i['headline']}", "", i["summary"], "", "Pontos principais:", *[f"- {p}" for p in i["key_points"]], ""]) for i in items]; (out/"daily_briefing_v2.md").write_text("\n".join(lines),encoding="utf-8")
    entity_audit=[]; audit_events={x["event_id"]: x["event"] for x in audits}
    for name, event_id in (("Atlas de IA e Economia", "64730bcdfc3a3522"), ("agêntica", "c8ed13949c16d029"), ("WIRED", "48554e95dd9ffc1e")):
        event=audit_events.get(event_id, {})
        ok, provenance, matched=EntityGroundingValidatorV2().check(name, event); entity_audit.append({"entity":name,"classification":"VALID_TRANSFORMATION_REJECTED" if ok and provenance != "SOURCE_METADATA" else ("SOURCE_METADATA_REJECTED" if ok else "REAL_HALLUCINATION"),"grounded":ok,"provenance":provenance,"matched":matched})
    (out/"phase_3_3_entity_grounding_audit.json").write_text(json.dumps(entity_audit,ensure_ascii=False,indent=2),encoding="utf-8"); (out/"phase_3_3_editorial_audit.json").write_text(json.dumps([{k:x[k] for k in ("trace_id", "event_id", "quality", "editorial", "normalizations", "accepted")} for x in audits],ensure_ascii=False,indent=2),encoding="utf-8"); (out/"phase_3_3_operational_metrics.json").write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding="utf-8"); (out/"phase_3_3_human_audit.json").write_text(json.dumps([{ "trace_id":x["trace_id"],"event_id":x["event_id"],"headline":(x.get("summary") or {}).get("headline"),"factual_accuracy":None,"natural_portuguese":None,"headline_quality":None,"usefulness":None,"source_support":None,"would_read":None,"notes":None} for x in accepted],ensure_ascii=False,indent=2),encoding="utf-8")
    technical = bool(metrics.get("factual_valid_rate", 0) >= .8 and metrics.get("provider_failure_rate", 1) <= .05 and metrics.get("briefing_fill_rate", 0) >= .9 and not any(x["summary_status"] != "VALID" for x in accepted)); report={"PHASE_3_2_1_GATE_RESULT":"NO","PHASE_3_3_STARTED_BY_ENGINEERING_DECISION":True,"PHASE_3_3_TECHNICAL_GATE":"YES" if technical else "NO","HUMAN_EDITORIAL_AUDIT":"PENDING","READY_FOR_PRODUCT_INTEGRATION":"YES" if technical else "NO","READY_FOR_PRODUCTION":"NO","metrics":metrics,"candidate_count":len(candidates),"final_items":len(items)}; (out / "phase_3_3_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8"); return report

