import os, time
from .cache import LLMCache
from .contracts import LLMRequest
from .validation import extract_json, SCHEMA_VERSION
PROMPT_VERSION="semantic_probe_v2"
SCHEMA_INSTRUCTION='''Return ONLY one JSON object with exactly these fields and types: {"main_entity": string, "event_type": string, "factuality": string, "is_news_event": boolean, "is_evergreen": boolean, "confidence": number between 0 and 1, "reason": string}. Do not use Markdown. Analyze this input:\n'''
class SemanticProbe:
    def __init__(self,provider,cache=None,max_retries=None): self.provider=provider; self.cache=cache or LLMCache(); self.max_retries=int(max_retries if max_retries is not None else os.getenv("LLM_MAX_RETRIES","2"))
    def run(self,event_id,content):
        request=LLMRequest(content,getattr(self.provider,"model",""),PROMPT_VERSION,SCHEMA_VERSION,event_id); key=self.cache.key(content,request.model,request.prompt_version,request.schema_version); cached=self.cache.get(key)
        if cached: self.cache.log(event_id=event_id,provider=self.provider.name,model=request.model,prompt_version=PROMPT_VERSION,input_size=len(content),attempt=0,cache_hit=True,validation_result="CACHE_HIT"); return {"status":"cache_hit","result":cached,"attempts":0}
        prompt=SCHEMA_INSTRUCTION+content; errors=[]
        for attempt in range(1,self.max_retries+2):
            started=time.perf_counter()
            try:
                response=self.provider.generate(LLMRequest(prompt,request.model,request.prompt_version,request.schema_version,event_id)); result=extract_json(response.text); latency=(time.perf_counter()-started)*1000; meta={"provider":self.provider.name,"model":request.model,"prompt_version":PROMPT_VERSION,"schema_version":SCHEMA_VERSION}; self.cache.put(key,meta,result); self.cache.log(event_id=event_id,provider=self.provider.name,model=request.model,prompt_version=PROMPT_VERSION,input_size=len(prompt),attempt=attempt,latency_ms=latency,validation_result="accepted"); return {"status":"accepted","result":result,"attempts":attempt,"latency_ms":latency,"input_tokens":response.input_tokens,"output_tokens":response.output_tokens}
            except Exception as exc:
                errors.append(str(exc)); self.cache.log(event_id=event_id,provider=self.provider.name,model=request.model,prompt_version=PROMPT_VERSION,input_size=len(prompt),attempt=attempt,latency_ms=(time.perf_counter()-started)*1000,validation_result="rejected",error=str(exc)); prompt=SCHEMA_INSTRUCTION+content+"\nPrevious error: "+str(exc)
        return {"status":"rejected","errors":errors,"attempts":self.max_retries+1}

