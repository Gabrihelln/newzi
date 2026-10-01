"""Conservative article content acquisition and evidence-pack construction."""
import hashlib, re, sqlite3, time
from datetime import datetime, timezone
from html.parser import HTMLParser
import httpx
from newzi_engine.paths import ENGINE_DATA

class _TextExtractor(HTMLParser):
    SKIP={"script","style","noscript","nav","footer","header","aside","form","svg"}
    def __init__(self): super().__init__(); self.skip=0; self.parts=[]; self.title=""
    def handle_starttag(self,tag,attrs):
        if tag in self.SKIP: self.skip+=1
        if tag=="title": self.title=""
    def handle_endtag(self,tag):
        if tag in self.SKIP and self.skip: self.skip-=1
    def handle_data(self,data):
        if not self.skip:
            text=re.sub(r"\s+"," ",data).strip()
            if text: self.parts.append(text)
            if not self.title and len(self.parts)==1: self.title=text

def clean_page(html):
    parser=_TextExtractor(); parser.feed(html); text="\n".join(parser.parts); text=re.sub(r"(?i)(accept cookies|cookie settings|subscribe to our newsletter|sign up for our newsletter|related stories).*?(?=\n|$)","",text); return re.sub(r"\n{2,}","\n",text).strip()

class ArticleContentResolver:
    def __init__(self,cache_path=None,timeout=8,max_bytes=2_000_000,user_agent="NewsEngine/3.2",retries=1):
        cache_path = cache_path or (ENGINE_DATA / "news_engine_content.sqlite3")
        self.timeout=timeout; self.max_bytes=max_bytes; self.user_agent=user_agent; self.retries=retries; self.db=sqlite3.connect(cache_path); self.db.execute("CREATE TABLE IF NOT EXISTS content_cache(url_hash TEXT PRIMARY KEY,url TEXT,content TEXT,content_hash TEXT,fetched_at TEXT,http_status INTEGER,content_type TEXT,method TEXT)"); self.db.commit()
    def _cache(self,url): return self.db.execute("SELECT * FROM content_cache WHERE url_hash=?",(hashlib.sha256(url.encode()).hexdigest(),)).fetchone()
    def _put(self,url,content,status,ctype,method): self.db.execute("INSERT OR REPLACE INTO content_cache VALUES(?,?,?,?,?,?,?,?)",(hashlib.sha256(url.encode()).hexdigest(),url,content,hashlib.sha256(content.encode()).hexdigest(),datetime.now(timezone.utc).isoformat(),status,ctype,method)); self.db.commit()
    def resolve(self,article):
        started=time.perf_counter(); title=article.get("title","") if isinstance(article,dict) else getattr(article,"title",""); description=article.get("description","") if isinstance(article,dict) else getattr(article,"description",""); url=article.get("url","") if isinstance(article,dict) else getattr(article,"url",""); existing=article.get("content") or article.get("content_encoded") if isinstance(article,dict) else ""
        if existing and len(existing)>300: return self._result(title,existing,"RSS_FULL","HIGH",False,None,None,started)
        if description and len(description)>160: return self._result(title,description,"DESCRIPTION_ONLY","MEDIUM",False,None,None,started)
        cached=self._cache(url) if url else None
        if cached and len(cached[2])>300: return self._result(title,cached[2],"PAGE_EXTRACTED","HIGH",True,cached[5],cached[6],started)
        if not url: return self._result(title,description or title,"DESCRIPTION_ONLY" if description else "TITLE_ONLY","MEDIUM" if description else "LOW",False,None,None,started)
        try:
            for attempt in range(self.retries+1):
                with httpx.stream("GET",url,headers={"User-Agent":self.user_agent,"Accept":"text/html,application/xhtml+xml"},timeout=self.timeout,follow_redirects=True,limits=httpx.Limits(max_connections=4)) as response:
                    ctype=response.headers.get("content-type","").lower()
                    if response.status_code>=400: return self._result(title,description or title,"DESCRIPTION_ONLY" if description else "TITLE_ONLY","MEDIUM" if description else "LOW",True,response.status_code,ctype,started,"CONTENT_UNAVAILABLE")
                    if "html" not in ctype: return self._result(title,description or title,"DESCRIPTION_ONLY" if description else "TITLE_ONLY","MEDIUM" if description else "LOW",True,response.status_code,ctype,started,"CONTENT_UNAVAILABLE")
                    chunks=[]; total=0
                    for chunk in response.iter_bytes():
                        total+=len(chunk)
                        if total>self.max_bytes: break
                        chunks.append(chunk)
                    html=b"".join(chunks).decode(response.encoding or "utf-8",errors="replace"); text=clean_page(html)
                    if len(text)>500:
                        self._put(url,text,response.status_code,ctype,"PAGE_EXTRACTED"); return self._result(title,text,"PAGE_EXTRACTED","HIGH",True,response.status_code,ctype,started)
            return self._result(title,description or title,"DESCRIPTION_ONLY" if description else "TITLE_ONLY","MEDIUM" if description else "LOW",True,200,"text/html",started,"CONTENT_UNAVAILABLE")
        except Exception:
            return self._result(title,description or title,"DESCRIPTION_ONLY" if description else "TITLE_ONLY","MEDIUM" if description else "LOW",True,None,None,started,"CONTENT_UNAVAILABLE")
    def _result(self,title,text,method,quality,attempted,http_status,ctype,started,error=None): return {"title":title,"evidence_text":text,"content_source":method,"evidence_quality":quality,"fetch_attempted":attempted,"fetch_status":"SUCCESS" if not error else error,"http_status":http_status,"content_type":ctype,"bytes_received":len(text.encode()),"extraction_method":method,"extracted_characters":len(text),"latency_ms":round((time.perf_counter()-started)*1000,2)}

def build_evidence_pack(event,resolver):
    articles=[]; observations=[]
    for i,article in enumerate(event.get("articles",[]),1):
        record={"article_id":f"article_{i:02d}","publisher":article.get("source",article.get("source_name","")),"source_language":article.get("source_language",article.get("language","unknown")),"published_at":article.get("published_at"),"url":article.get("url","")}; acquired=resolver.resolve(article); record.update({k:acquired[k] for k in ("content_source","evidence_text","evidence_quality")}); articles.append(record); observations.append({"article_id":record["article_id"],**{k:acquired[k] for k in ("fetch_attempted","fetch_status","http_status","content_type","bytes_received","extraction_method","extracted_characters","evidence_quality","latency_ms")}})
    quality="HIGH" if articles and all(a["evidence_quality"]=="HIGH" for a in articles) else ("MEDIUM" if any(a["evidence_quality"]=="MEDIUM" for a in articles) else "LOW")
    return {"schema_version":"evidence_pack_v1","event_id":event.get("event_id"),"articles":articles,"event_evidence_quality":quality,"observability":observations}

