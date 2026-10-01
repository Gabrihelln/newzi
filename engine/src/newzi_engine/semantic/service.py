import json, time
from datetime import datetime, timezone
from newzi_engine.llm.contracts import LLMRequest
from newzi_engine.llm.cache import LLMCache
from .schemas import validate_classifier, validate_verifier
from .validator import SemanticOutputValidator
from .reliability import semantic_reliability_score, reliability_gate, deterministic_agreement

class SemanticService:
    def __init__(self,provider,cache=None,retries=1):
        self.provider=provider; self.cache=cache or LLMCache(); self.retries=retries
        self.cache.db.execute("CREATE TABLE IF NOT EXISTS semantic_event_analysis(id INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT,provider TEXT,model TEXT,prompt_version TEXT,schema_version TEXT,input_hash TEXT,result_json TEXT,confidence REAL,created_at TEXT)"); self.cache.db.commit()
    def call(self, event_id, prompt, prompt_version, schema_version, validator, max_evidence, use_cache=True, event=None, temperature=0.0, deterministic=None, consistency=1.0):
        model=getattr(self.provider,"model",""); key=self.cache.key(prompt,model,prompt_version,schema_version)
        if use_cache:
            cached=self.cache.get(key)
            if cached: return {"status":"cache_hit","result":cached,"attempts":0,"latency_ms":0}
        errors=[]; current=prompt
        for attempt in range(1,self.retries+2):
            started=time.perf_counter()
            try:
                response=self.provider.generate(LLMRequest(current,model,prompt_version,schema_version,event_id,temperature)); checked=validator(response.text,max_evidence) if event is None else validator(response.text,event,max_evidence)
                semantic_status=getattr(checked,"status",None) or "VALID"; result=getattr(checked,"result",checked)
                if semantic_status == "INVALID": raise ValueError("semantic_status=INVALID; "+"; ".join(getattr(checked,"errors",[])))
                latency=(time.perf_counter()-started)*1000
                if semantic_status == "VALID" and use_cache: self.cache.put(key,{"provider":self.provider.name,"model":model,"prompt_version":prompt_version,"schema_version":schema_version},result)
                self.cache.log(event_id=event_id,provider=self.provider.name,model=model,prompt_version=prompt_version,input_size=len(current),attempt=attempt,latency_ms=latency,validation_result=semantic_status.lower())
                self.cache.db.execute("INSERT INTO semantic_event_analysis(event_id,provider,model,prompt_version,schema_version,input_hash,result_json,confidence,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(event_id,self.provider.name,model,prompt_version,schema_version,key,json.dumps(result,ensure_ascii=False),result.get("confidence",0),datetime.now(timezone.utc).isoformat())); self.cache.db.commit()
                payload={"status":"accepted","semantic_status":semantic_status,"validation_codes":getattr(checked,"codes",[]),"result":result,"attempts":attempt,"latency_ms":latency,"input_tokens":response.input_tokens,"output_tokens":response.output_tokens}
                if event is not None:
                    agreement=deterministic_agreement(result,deterministic)
                    score, components=semantic_reliability_score(result,semantic_status,getattr(checked,"codes",[]),event,agreement,consistency)
                    payload["semantic_reliability_score"]=score; payload["reliability_components"]=components; payload["reliability_gate"]=reliability_gate(score,semantic_status,getattr(checked,"codes",[]))
                return payload
            except Exception as exc:
                errors.append(str(exc)); self.cache.log(event_id=event_id,provider=self.provider.name,model=model,prompt_version=prompt_version,input_size=len(current),attempt=attempt,latency_ms=(time.perf_counter()-started)*1000,validation_result="rejected",error=str(exc)); current=prompt+"\nReturn only valid JSON matching every field. Previous validation error: "+str(exc)
        semantic_status="INVALID" if any("semantic_status=INVALID" in error for error in errors) else "PROVIDER_FAILED"
        return {"status":"rejected","semantic_status":semantic_status,"errors":errors,"attempts":self.retries+1}

class SemanticClassifier:
    prompt_version="semantic_classifier_v3"; schema_version="semantic_event_v2"
    def __init__(self,service,variant="zero_shot"): self.service=service; self.variant=variant
    def classify(self,event,use_cache=True,deterministic=None,consistency=1.0):
        prompt="""TASK: classify the supplied article conservatively. Use only INPUT evidence. If evidence is insufficient or ambiguous, use decision ABSTAIN. Never invent an entity, number, date, or claim.\nDEFINITIONS: main_entity is a named organization, person, institution, or product central to the article; null is correct when unclear. newsworthiness is INTEGER 0-100: 5 negligible, 25 low, 50 moderate, 75 high, 90 very important, 100 exceptional. confidence is 0.0-1.0: 0.50 uncertain, 0.70 reasonable, 0.85 high, 0.95 very high; never use 1.0 by default.\nRULES: event_type must be one of the allowed enum values. evidence_indices must point to supplied article indices. decision is CLASSIFIED or ABSTAIN. abstain_reason is null for CLASSIFIED, otherwise one of INSUFFICIENT_EVIDENCE, AMBIGUOUS_EVENT, ENTITY_UNCLEAR, CONTENT_TYPE_UNCLEAR, CONFLICTING_EVIDENCE.\nOUTPUT SCHEMA: {"decision":"CLASSIFIED","abstain_reason":null,"main_entity":null,"secondary_entities":[],"event_subject":"","event_type":"OTHER","is_news_event":false,"is_evergreen":false,"is_analysis":false,"is_opinion":false,"is_promotional":false,"topic_categories":[],"newsworthiness":50,"confidence":0.7,"reasoning_summary":"","core_factual_claim":"","evidence_indices":[0]}\nALLOWED EVENT TYPES: """+",".join(sorted(__import__('newzi_engine.semantic.schemas',fromlist=['EVENT_TYPES']).EVENT_TYPES))+"\nINPUT:\n"+json.dumps(event,ensure_ascii=False)
        if self.variant == "few_shot": prompt += "\nEXAMPLES: {\"decision\":\"ABSTAIN\",\"abstain_reason\":\"ENTITY_UNCLEAR\"} and {\"decision\":\"CLASSIFIED\",\"main_entity\":\"Acme\",\"event_type\":\"NEWS_EVENT\",\"newsworthiness\":75,\"confidence\":0.85}"
        strict = SemanticOutputValidator(strict=False if self.service.provider.name == "mock" else True)
        return self.service.call(event.get("event_id",""),prompt,self.prompt_version,self.schema_version,strict.validate_classifier,len(event.get("articles",[])),use_cache,event,0.0,deterministic,consistency)

class SemanticClusterVerifier:
    prompt_version="semantic_cluster_verifier_v3"; schema_version="semantic_cluster_v1"
    def __init__(self,service,accept_threshold=.85,uncertain_threshold=.65): self.service=service; self.accept_threshold=accept_threshold; self.uncertain_threshold=uncertain_threshold
    def verify(self,left,right,use_cache=True):
        prompt="""Compare two candidate articles. Use only supplied evidence. Same company, product, topic, or publisher is not sufficient. Decide whether they describe the SAME concrete event. Return ONLY one valid JSON object with exactly these fields and types. decision MUST be SAME_EVENT, DIFFERENT_EVENT, or UNCERTAIN. same_event is true only for SAME_EVENT, false otherwise. evidence_indices must be integer indices referring to the supplied article evidence.\nJSON TEMPLATE:\n{"decision":"UNCERTAIN","same_event":false,"confidence":0.0,"shared_event":"","reason":"","evidence_indices":[]}\nA:\n"""+json.dumps(left,ensure_ascii=False)+"\nB:\n"+json.dumps(right,ensure_ascii=False)
        strict=SemanticOutputValidator(strict=False if self.service.provider.name == "mock" else True)
        verifier_validator=lambda text, max_evidence: strict.validate_verifier(text,left,right,max_evidence)
        result=self.service.call(left.get("article_id","")+"|"+right.get("article_id",""),prompt,self.prompt_version,self.schema_version,verifier_validator,10,use_cache)
        if result.get("status") in {"accepted","cache_hit"}:
            value=result["result"]; confidence=float(value["confidence"])
            if confidence < self.uncertain_threshold: value["decision"]="UNCERTAIN"
            elif confidence < self.accept_threshold: value["decision"]="UNCERTAIN"
        return result

