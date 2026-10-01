"""Hybrid editorial router: deterministic candidates plus constrained LLM disambiguation."""
import json, re
from dataclasses import dataclass, asdict
from .hierarchy import SIGNALS, support_signal, family_for_type, family_support
from .validator import evidence_text, norm, SemanticValidation
from newzi_engine.llm.validation import parse_json_object
from newzi_engine.semantic.reliability import reliability_gate

ABSTAIN_REASONS={"NO_STRONG_CANDIDATE","CONFLICTING_CANDIDATES","INSUFFICIENT_EVIDENCE","LLM_UNCERTAIN"}

@dataclass
class Candidate:
    type: str
    score: float
    signals: list[str]

class EventTypeCandidateGenerator:
    """High-precision evidence detector. Scores are evidence strength, not probabilities."""
    def generate(self,event):
        text=evidence_text(event); out=[]
        def add(kind,score,signals):
            if signals: out.append(Candidate(kind,min(0.99,score),signals))
        # Compositional signals for the specific factual types.
        for kind,terms in SIGNALS.items():
            hits=[term for term in terms if norm(term) in text]
            if not hits: continue
            score=.55 + .12*min(3,len(hits))
            if kind in {"FUNDING","ACQUISITION","REGULATION","RESEARCH"}:
                score=.55 + (.18 if len(hits)>=2 else 0) + (.12 if len(text.split())>4 else 0)
            add(kind,score,hits[:4])
        if any(x in text for x in ("interview","entrevista","entrevue")): add("INTERVIEW",.91,["interview"])
        if any(x in text for x in ("review","review:","avaliação","reseña","critique")): add("REVIEW",.91,["review"])
        if any(x in text for x in ("roundup","weekly roundup","resumo da semana","recap")): add("ROUNDUP",.90,["roundup"])
        if any(x in text for x in ("opinion:","op-ed","opinião","opinion ")): add("OPINION",.90,["opinion"])
        if any(x in text for x in ("analysis","análise","analyse")): add("ANALYSIS",.86,["analysis"])
        extra={"COMPANY_ANNOUNCEMENT":("expands","expanded","changes eu","subscription plans","going public","ipo","partnership","appoints","opens a new","ceo says","ceo commented","plans to","reports quarterly","revenue growth","cuts thousands of jobs","empresa anuncia","parceria"),"PRODUCT_ANNOUNCEMENT":("keynote","presented","platform","features","refresh","new model","new product","announced a new","lanca","lança","apresentou"),"LEGAL":("seizes","seized","authorities","action against","takes action","recall","recalls"),"HOW_TO":("ways to","users can use","practical guide","setup","configure","steps"),"EVERGREEN":("guide","explains","tips","best practices","history of","explained"),"REGULATION":("ley","debate una nueva ley"),"ACQUISITION":("adquiere",)}
        for kind,terms in extra.items():
            hits=[term for term in terms if norm(term) in text]
            if hits: add(kind,.68 if kind=="EVERGREEN" else .74,hits[:4])
        # General factual-news support is intentionally weaker than specific candidates.
        if re.search(r"\b(expects|warns|increases|seizes|passes|discusses|says|takes|releases)\w*\b",text): add("NEWS_EVENT",.25,["factual-news"])
        if "catalog" in text: add("PROMOTION",.74,["catalog"])
        if re.search(r"\b(announc|launch|raises|raised|study|research|law|regulation|court|acqui|fund|anuncia|lança|publica|publie)\w*\b",text): add("NEWS_EVENT",.25,[])
        # Keep only the strongest evidence for each type and suppress weak NEWS_EVENT when a specific type exists.
        merged={}
        for c in out:
            if c.type not in merged or c.score>merged[c.type].score: merged[c.type]=c
        candidates=sorted(merged.values(),key=lambda c:(c.score,c.type),reverse=True)
        if candidates and any(c.type!="NEWS_EVENT" and c.score>=.72 for c in candidates): candidates=[c for c in candidates if c.type!="NEWS_EVENT"]+ [c for c in candidates if c.type=="NEWS_EVENT" and c.score>=.5]
        return [asdict(c) for c in sorted(candidates,key=lambda c:c.score,reverse=True)[:3]]

class PairEvidenceComparator:
    """Deterministic audit helper; it never merges events by itself."""
    def compare(self,left,right):
        lt=norm((left.get("title","")+" "+left.get("description","")).strip()); rt=norm((right.get("title","")+" "+right.get("description","")).strip())
        stop={"the","a","an","of","and","in","to","for","new","with","da","de","do","uma","um"}
        lset={x for x in re.findall(r"[a-z0-9]+",lt) if len(x)>2 and x not in stop}; rset={x for x in re.findall(r"[a-z0-9]+",rt) if len(x)>2 and x not in stop}; overlap=sorted(lset & rset)
        conflict=any(a in lt and b in rt or b in lt and a in rt for a,b in (("fund","acqui"),("siri","pencil"),("xc60","xc90"),("paris","tokyo"),("model 3","model y"),("report","launch")))
        safe=len(overlap)>=2 and not conflict
        return {"token_overlap":overlap,"conflict":conflict,"safe_same_event":safe}

def derive_flags(event_type, original=None):
    flags=dict(original or {})
    if event_type in {"HOW_TO","BUYING_GUIDE","REVIEW","ROUNDUP","EVERGREEN"}: flags["is_news_event"]=False
    if event_type=="PROMOTION": flags.update(is_promotional=True,is_news_event=False)
    if event_type=="ANALYSIS": flags.update(is_analysis=True,is_news_event=False)
    if event_type=="OPINION": flags.update(is_opinion=True,is_news_event=False)
    if event_type in {"FUNDING","ACQUISITION","REGULATION","LEGAL","RESEARCH","PRODUCT_ANNOUNCEMENT","COMPANY_ANNOUNCEMENT","NEWS_EVENT"}: flags.setdefault("is_news_event",True)
    return flags

def validate_disambiguator(text,event,max_evidence=20):
    try: raw=parse_json_object(text)
    except Exception as exc: return SemanticValidation("INVALID",errors=[str(exc)],codes=["OUTPUT_INVALID"])
    if set(raw)-{"decision","event_type","confidence","evidence_indices","abstain_reason"}: return SemanticValidation("INVALID",errors=["unexpected fields"],codes=["OUTPUT_INVALID"])
    if raw.get("decision") not in {"CLASSIFIED","ABSTAIN"}: return SemanticValidation("INVALID",errors=["invalid decision"],codes=["OUTPUT_INVALID"])
    if raw.get("decision")=="CLASSIFIED" and not raw.get("event_type"): return SemanticValidation("INVALID",errors=["classified without event_type"],codes=["OUTPUT_INVALID"])
    if raw.get("decision")=="CLASSIFIED" and raw.get("event_type") not in {c["type"] for c in event.get("candidates",[])}: return SemanticValidation("INVALID",errors=["event_type outside candidates"],codes=["OUTPUT_INVALID"])
    if not isinstance(raw.get("confidence"),(int,float)) or not 0 <= float(raw["confidence"]) <= 1: return SemanticValidation("INVALID",errors=["confidence outside range"],codes=["OUTPUT_INVALID"])
    if not isinstance(raw.get("evidence_indices"),list) or not all(isinstance(x,int) and 0<=x<max_evidence for x in raw["evidence_indices"]): return SemanticValidation("INVALID",errors=["invalid evidence_indices"],codes=["OUTPUT_INVALID"])
    if raw.get("decision")=="ABSTAIN":
        raw["event_type"]=None
        if raw.get("abstain_reason") not in ABSTAIN_REASONS: return SemanticValidation("INVALID",errors=["invalid abstain_reason"],codes=["OUTPUT_INVALID"])
        return SemanticValidation("VALID",raw,[],[])
    return SemanticValidation("VALID",raw,[],[])

class HybridEditorialRouter:
    prompt_version="hybrid_editorial_router_v1"; schema_version="hybrid_router_v1"
    def __init__(self,service,generator=None): self.service=service; self.generator=generator or EventTypeCandidateGenerator()
    def route(self,event,use_cache=False,deterministic=None):
        candidates=self.generator.generate(event); payload={"output_validity":"VALID","classification_decision":"ABSTAIN","confidence_state":"ABSTAIN","decision_source":"ABSTAIN","candidate_types":[x["type"] for x in candidates],"candidate_scores":candidates,"signals":[s for x in candidates for s in x["signals"]],"llm_used":False,"final_event_type":None,"confidence":0.0}
        if not candidates: payload["abstain_reason"]="NO_STRONG_CANDIDATE"; return payload
        strong=[x for x in candidates if x["score"]>=.84]
        if len(strong)==1 and all(x["score"]<.72 or x["type"]==strong[0]["type"] for x in candidates):
            final=strong[0]["type"]; payload.update(classification_decision="CLASSIFIED",confidence_state="TRUSTED",decision_source="DETERMINISTIC",final_event_type=final,confidence=strong[0]["score"],abstain_reason=None); return payload
        constrained={**event,"candidates":candidates}; prompt="TASK: choose only among CANDIDATES using supplied evidence. If none is sufficiently supported, ABSTAIN. Do not invent a type. Return only JSON with decision CLASSIFIED or ABSTAIN, event_type one of the candidates or null, confidence 0-1, evidence_indices, abstain_reason. CANDIDATES="+json.dumps(candidates,ensure_ascii=False)+" INPUT="+json.dumps(event,ensure_ascii=False)
        result=self.service.call(event.get("event_id",""),prompt,self.prompt_version,self.schema_version,lambda text,_event,max_evidence: validate_disambiguator(text,constrained,max_evidence),len(event.get("articles",[])),use_cache,event,0.0,deterministic)
        payload.update(llm_used=True,llm_result=result,decision_source="LLM_DISAMBIGUATION")
        if result.get("status") not in {"accepted","cache_hit"}: payload.update(output_validity="INVALID",classification_decision="ABSTAIN",confidence_state="INVALID",decision_source="ABSTAIN",abstain_reason="LLM_UNCERTAIN"); return payload
        value=result["result"]
        if value.get("decision")=="ABSTAIN": payload.update(classification_decision="ABSTAIN",confidence_state="ABSTAIN",decision_source="ABSTAIN",abstain_reason=value.get("abstain_reason"),confidence=value.get("confidence",0)); return payload
        final=value["event_type"]; support=next((x for x in candidates if x["type"]==final),None); conf=min(float(value["confidence"]),float(support["score"]) if support else 0); state="TRUSTED" if support and support["score"]>=.72 and conf>=.75 else "REVIEW"; payload.update(classification_decision="CLASSIFIED",confidence_state=state,final_event_type=final,confidence=conf,abstain_reason=None); return payload

