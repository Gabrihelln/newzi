import time
from datetime import timedelta
import feedparser, httpx
from ..models import Article, utc_now
from ..images import extract_feed_image
from ..utils.dates import parse_date
from ..utils.text import article_id, canonicalize_url, clean_text

class RSSCollector:
    def __init__(self, settings):
        req=settings.get("request",{}); self.connect_timeout=float(req.get("connect_timeout_seconds",4)); self.read_timeout=float(req.get("read_timeout_seconds",8)); self.write_timeout=float(req.get("write_timeout_seconds",4)); self.pool_timeout=float(req.get("pool_timeout_seconds",2)); self.source_budget=float(req.get("source_budget_seconds",12)); self.max_response_bytes=int(req.get("max_response_bytes",5_000_000)); self.max_age_days=int(req.get("max_age_days",30)); self.ua=req.get("user_agent","NewsEngine/0.1"); self.last_metrics={}; self.validators={}
    def collect(self, source, validators=None):
        started=time.perf_counter(); headers={"User-Agent":self.ua,"Accept":"application/atom+xml,application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.5"}; validators=validators or {}
        if validators.get("etag"): headers["If-None-Match"]=validators["etag"]
        if validators.get("last_modified"): headers["If-Modified-Since"]=validators["last_modified"]
        try:
            request_started=time.perf_counter()
            with httpx.stream("GET",source["feed_url"],headers=headers,timeout=httpx.Timeout(connect=self.connect_timeout,read=self.read_timeout,write=self.write_timeout,pool=self.pool_timeout),follow_redirects=True) as response:
                first_byte=time.perf_counter(); self.validators={"etag":response.headers.get("ETag"),"last_modified":response.headers.get("Last-Modified")}
                if response.status_code==304:
                    self.last_metrics={"status":"NOT_MODIFIED","http_status":304,"duration_ms":int((first_byte-started)*1000),"fetch_ms":int((first_byte-request_started)*1000),"ttfb_ms":int((first_byte-request_started)*1000),"download_ms":0,"parse_ms":0,"discovery_ms":0,"response_bytes":0,"articles_seen":0,"newest_article":None}
                    return [],None
                response.raise_for_status(); chunks=[]; response_size=0
                for chunk in response.iter_bytes():
                    response_size+=len(chunk)
                    if response_size>self.max_response_bytes: raise ValueError(f"feed exceeds {self.max_response_bytes} byte limit")
                    if time.perf_counter()-started>self.source_budget: raise TimeoutError(f"source exceeded {self.source_budget:.0f}s request budget")
                    chunks.append(chunk)
                body=b"".join(chunks)
            if time.perf_counter()-started>self.source_budget: raise TimeoutError(f"source exceeded {self.source_budget:.0f}s request budget")
            fetched=time.perf_counter(); parse_started=time.perf_counter(); parsed=feedparser.parse(body); parsed_at=time.perf_counter()
            if parsed.bozo and not parsed.entries: raise ValueError(str(parsed.bozo_exception))
            out=[]; now=utc_now(); newest=None; discovered=0
            for e in parsed.entries:
                title=clean_text(e.get("title")); url=canonicalize_url(e.get("link") or e.get("id") or "")
                if not title or not url: continue
                pub=parse_date(e.get("published") or e.get("updated") or e.get("created"))
                if pub and pub < now-timedelta(days=self.max_age_days): continue
                if pub and (newest is None or pub>newest): newest=pub
                cats=source.get("categories",[]); discovered+=1
                image_url,image_source=extract_feed_image(e,url)
                out.append(Article(article_id(source["id"],url,title),source["id"],source["name"],title,clean_text(e.get("summary") or e.get("description")),url,url,pub,now,source.get("language","en"),cats,[],source.get("source_type","JOURNALISM"),e.get("author"),source.get("publisher_id",source["id"]),image_url=image_url,image_source=image_source))
            finished=time.perf_counter(); self.last_metrics={"status":"SUCCESS","http_status":response.status_code,"duration_ms":int((finished-started)*1000),"fetch_ms":int((fetched-request_started)*1000),"ttfb_ms":int((first_byte-request_started)*1000),"download_ms":int((fetched-first_byte)*1000),"parse_ms":int((parsed_at-parse_started)*1000),"discovery_ms":int((finished-parsed_at)*1000),"response_bytes":len(body),"articles_seen":discovered,"newest_article":newest.isoformat() if newest else None,"etag":self.validators.get("etag"),"last_modified":self.validators.get("last_modified")}
            return out,None
        except Exception as exc:
            finished=time.perf_counter(); self.last_metrics={"status":"FAILED","http_status":getattr(getattr(exc,"response",None),"status_code",None),"duration_ms":int((finished-started)*1000),"fetch_ms":int((finished-started)*1000),"parse_ms":0,"discovery_ms":0,"response_bytes":0,"articles_seen":0,"newest_article":None}
            return [],str(exc)

