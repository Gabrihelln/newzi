"""Grounded factual event summarization for Phase 3.1."""
import json, os, re, time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from .validator import SemanticValidation, norm
from newzi_engine.llm.validation import parse_json_object

SUMMARY_FIELDS={"headline","summary","why_it_matters","key_points","entities","source_refs","factual_claims","source_conflict","confidence","status"}
SUPPORTS={"DIRECT","MULTI_SOURCE","PARTIAL"}
ENTITY_ALIASES={"gm":"general motors","general motors":"gm","ai":"artificial intelligence","artificial intelligence":"ai","ia":"inteligência artificial","inteligência artificial":"ia","custom fiction":"ficção personalizada","ficção personalizada":"custom fiction"}
COMMON_ENTITY_TERMS={"empresa","company","plataforma","platform","ia","ai","segurança","security","agente","agent","previsão","prediction","visibilidade","visibility","observabilidade","observability","economia","economy","leitores","readers","ficção personalizada","custom fiction","indústria editorial","publishing industry"}

def _text(event):
    parts=[event.get("representative_title"),event.get("title"),event.get("description")]+[a.get("title","")+" "+a.get("description","") for a in event.get("articles",[])]
    return " ".join(str(x or "") for x in parts)
def _numbers(text): return {x.replace(",",".") for x in re.findall(r"(?<![A-Za-z])\d+(?:[.,]\d+)?",text)}
def _years_dates(text): return set(re.findall(r"\b(?:19|20)\d{2}\b|\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b",text))
def _entity_grounded(entity,source):
    value=norm(entity); source_norm=norm(source)
    if value in COMMON_ENTITY_TERMS: return True
    if value in source_norm: return True
    alias=ENTITY_ALIASES.get(value)
    return bool(alias and alias in source_norm)

@dataclass
class SummaryResult:
    status: str
    result: dict|None=None
    errors: list[str]|None=None
    codes: list[str]|None=None

class SummaryGroundingValidator:
    entity_validator_cls = None
    def validate(self,text,event,max_evidence=20):
        try: raw=parse_json_object(text)
        except Exception as exc: return SemanticValidation("INVALID",errors=[str(exc)],codes=["INVALID_OUTPUT"])
        if isinstance(raw,dict):
            if isinstance(raw.get("status"),str): raw["status"]=raw["status"].upper()
            if isinstance(raw.get("confidence"),str):
                try: raw["confidence"]=float(raw["confidence"])
                except ValueError: pass
            if isinstance(raw.get("source_refs"),list): raw["source_refs"]=[x.get("id") or x.get("article_id") if isinstance(x,dict) else x for x in raw["source_refs"]]
            if isinstance(raw.get("factual_claims"),list):
                for claim in raw["factual_claims"]:
                    if isinstance(claim,dict):
                        if isinstance(claim.get("support"),str): claim["support"]=claim["support"].upper()
                        if isinstance(claim.get("source_refs"),list): claim["source_refs"]=[x.get("id") or x.get("article_id") if isinstance(x,dict) else x for x in claim["source_refs"]]
        errors=[]; codes=[]
        if set(raw)-SUMMARY_FIELDS: errors.append("unexpected fields"); codes.append("INVALID_OUTPUT")
        required={"headline","summary","key_points","entities","source_refs","factual_claims","source_conflict","confidence","status"}
        if not required <= set(raw): errors.append("missing summary fields"); codes.append("INVALID_OUTPUT")
        if raw.get("status") not in {"VALID","REVIEW","ABSTAIN","INVALID","PROVIDER_FAILED"}: errors.append("invalid status"); codes.append("INVALID_OUTPUT")
        if not isinstance(raw.get("headline"),str) or not raw.get("headline").strip(): errors.append("empty headline"); codes.append("EMPTY_OUTPUT")
        if not isinstance(raw.get("summary"),str) or not raw.get("summary").strip(): errors.append("empty summary"); codes.append("EMPTY_OUTPUT")
        if not isinstance(raw.get("key_points"),list) or not 2<=len(raw.get("key_points",[]))<=4: errors.append("key_points must contain 2-4 items"); codes.append("INVALID_OUTPUT")
        if not isinstance(raw.get("entities"),list) or not isinstance(raw.get("source_refs"),list) or any(not isinstance(x,str) for x in raw.get("source_refs",[]) if isinstance(raw.get("source_refs"),list)): errors.append("invalid list fields"); codes.append("INVALID_OUTPUT")
        if not isinstance(raw.get("factual_claims"),list): errors.append("factual_claims must be a list"); codes.append("INVALID_OUTPUT")
        if not isinstance(raw.get("confidence"),(int,float)) or not 0<=float(raw.get("confidence",-1))<=1: errors.append("confidence outside range"); codes.append("INVALID_OUTPUT")
        article_ids={f"article_{i:02d}" for i,_ in enumerate(event.get("articles",[]),1)}
        refs={x for x in raw.get("source_refs",[]) if isinstance(x,str)} if isinstance(raw.get("source_refs"),list) else set()
        if not refs <= article_ids: errors.append("source_refs outside supplied articles"); codes.append("SOURCE_REF_INVALID")
        for claim in raw.get("factual_claims",[]) if isinstance(raw.get("factual_claims"),list) else []:
            if not isinstance(claim,dict) or not isinstance(claim.get("claim"),str) or not claim.get("claim"): errors.append("invalid claim"); codes.append("INVALID_OUTPUT"); continue
            claim_refs=claim.get("source_refs",[])
            if not isinstance(claim_refs,list) or not all(isinstance(x,str) for x in claim_refs) or not set(claim_refs) <= article_ids: errors.append("claim source ref invalid"); codes.append("SOURCE_REF_INVALID")
            if claim.get("support") not in SUPPORTS: errors.append("claim support invalid"); codes.append("INVALID_OUTPUT")
        source=_text(event); generated=" ".join([raw.get("headline",""),raw.get("summary","")," ".join(raw.get("key_points",[]))," ".join(c.get("claim","") for c in raw.get("factual_claims",[]) if isinstance(c,dict))])
        source_nums=_numbers(source); generated_nums=_numbers(generated)
        if generated_nums-source_nums: errors.append("generated number not present in source"); codes.append("NUMBER_HALLUCINATION")
        source_dates=_years_dates(source); generated_dates=_years_dates(generated)
        if generated_dates-source_dates: errors.append("generated date/year not present in source"); codes.append("DATE_HALLUCINATION")
        entity_checker = self.entity_validator_cls() if self.entity_validator_cls else None
        for entity in raw.get("entities",[]) if isinstance(raw.get("entities"),list) else []:
            grounded = entity_checker.check(entity, event)[0] if entity_checker else _entity_grounded(entity,source)
            if not isinstance(entity,str) or not entity.strip() or not grounded: errors.append(f"entity not grounded: {entity}"); codes.append("ENTITY_HALLUCINATION")
        if errors: return SemanticValidation("INVALID",raw,errors,sorted(set(codes)))
        if raw.get("status")=="ABSTAIN": return SemanticValidation("ABSTAINED",raw,[],[])
        return SemanticValidation("VALID" if raw.get("status")=="VALID" else "REVIEW",raw,[],[])

class SemanticSummarizer:
    prompt_version="semantic_summarizer_v1"; schema_version="daily_summary_v1"
    def __init__(self,service): self.service=service; self.validator=SummaryGroundingValidator()
    def summarize(self,event,target_language="pt-BR",use_cache=False):
        articles=[]
        evidence_limit=max(400,int(os.getenv("NEWS_SUMMARY_EVIDENCE_CHARS","1200")))
        for i,a in enumerate(event.get("articles",[]),1):
            description=a.get("description",a.get("content","")) or ""
            articles.append({"id":f"article_{i:02d}","title":a.get("title","")[:240],"description":description[:evidence_limit],"source":a.get("source",a.get("source_name","")),"publisher_id":a.get("publisher_id",""),"published_at":a.get("published_at"),"url":a.get("url","")})
        if not articles or not any(a["title"] or a["description"] for a in articles): return {"status":"ABSTAIN","result":None,"validation_status":"ABSTAINED","grounding_errors":["EMPTY_INPUT"],"attempt_count":0,"cache_hit":False}
        prompt=("TASK: produce one factual, structured summary of this EVENT in "+target_language+". Use ONLY the supplied article evidence; do not use prior knowledge. "
        "Preserve attribution (e.g. 'segundo a empresa', 'o relatório aponta') and do not turn claims into facts. If evidence is insufficient or conflicting, use status REVIEW or ABSTAIN. "
        "Every factual_claim must cite one or more local source IDs. Never invent URLs. Return ONLY JSON with exactly: headline, summary, why_it_matters, key_points, entities, source_refs, factual_claims, source_conflict, confidence, status. "
        "headline must be short, non-clickbait, in pt-BR; summary 60-100 words when evidence supports it; why_it_matters null or <=40 words; key_points exactly 2-4 strings. factual_claims have claim, source_refs, support DIRECT/MULTI_SOURCE/PARTIAL. Return only the required JSON object. EVENT="+json.dumps({"event_id":event.get("event_id"),"representative_title":event.get("representative_title"),"articles":articles,"primary_entities":event.get("primary_entities",[]),"target_language":target_language},ensure_ascii=False))
        if self.prompt_version == "semantic_summarizer_v2": prompt += "\nEDITORIAL STYLE V2: write natural "+("Brazilian Portuguese" if target_language=="pt-BR" else target_language)+", never translate word-for-word; use 2-4 sentences when evidence supports it; do not add context to reach a length; if evidence is limited, be concise; key_points must complement rather than repeat headline or summary; why_it_matters is optional and only allowed when explicitly grounded; preserve names, numbers and dates; no promotional, speculative or opinion language."
        started=time.perf_counter(); result=self.service.call(event.get("event_id",""),prompt,self.prompt_version,self.schema_version,self.validator.validate,len(articles),use_cache,event,0.0)
        payload={"event_id":event.get("event_id"),"provider":getattr(self.service.provider,"name","unknown"),"model":getattr(self.service.provider,"model",""),"prompt_version":self.prompt_version,"schema_version":self.schema_version,"target_language":target_language,"input_articles":len(articles),"input_characters":len(prompt),"input_tokens":result.get("input_tokens"),"output_tokens":result.get("output_tokens"),"latency_ms":result.get("latency_ms",(time.perf_counter()-started)*1000),"cache_hit":result.get("status")=="cache_hit","attempt_count":result.get("attempts",0),"validation_status":result.get("semantic_status", "VALID" if result.get("status")=="cache_hit" else result.get("status")),"grounding_errors":result.get("validation_codes",[]),"timestamp":datetime.now(timezone.utc).isoformat(),"status":"VALID" if result.get("status")=="cache_hit" or (result.get("status")=="accepted" and result.get("semantic_status") in {"VALID","REVIEW","ABSTAINED"}) else ("PROVIDER_FAILED" if result.get("semantic_status")=="PROVIDER_FAILED" else "INVALID"),"result":result.get("result")}
        if payload["status"]=="INVALID" and result.get("errors"): payload["grounding_errors"]=[*payload["grounding_errors"],*result["errors"]]
        return payload

