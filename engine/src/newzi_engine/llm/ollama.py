import os, time, httpx
from .contracts import LLMProvider, LLMRequest, LLMResponse
class OllamaProvider(LLMProvider):
    name="ollama"
    def __init__(self, base_url="http://localhost:11434", model="", timeout=60, max_retries=2, max_output_tokens=None, context_length=None):
        self.base_url=base_url.rstrip("/"); self.model=model; self.timeout=timeout; self.max_retries=max_retries
        self.max_output_tokens=max_output_tokens if max_output_tokens is not None else int(os.getenv("OLLAMA_MAX_OUTPUT_TOKENS", "256"))
        self.context_length=context_length if context_length is not None else int(os.getenv("OLLAMA_CONTEXT_LENGTH", "4096"))
    def health_check(self):
        try:
            r=httpx.get(f"{self.base_url}/api/tags",timeout=min(self.timeout,5)); r.raise_for_status(); return {"available":True,"models":[m.get("name") for m in r.json().get("models",[])]}
        except Exception as exc: return {"available":False,"error":str(exc),"models":[]}
    def generate(self, request: LLMRequest):
        payload={"model":request.model,"prompt":request.input_text,"format":"json","stream":False,"options":{"num_predict":self.max_output_tokens,"num_ctx":self.context_length}}
        if request.temperature is not None: payload["options"]["temperature"]=request.temperature
        started=time.perf_counter(); r=httpx.post(f"{self.base_url}/api/generate",json=payload,timeout=self.timeout); r.raise_for_status(); data=r.json(); return LLMResponse(data.get("response",""),(time.perf_counter()-started)*1000,data.get("prompt_eval_count"),data.get("eval_count"),data)

