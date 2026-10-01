import json
from pathlib import Path
from ..models import iso
from ..paths import ENGINE_OUTPUT

def select_events(events, limit=10):
    selected=[]; counts={}; entities={}; max_per_entity=2
    for e in events:
        primary=e.categories[0] if e.categories else "other"
        penalty=counts.get(primary,0)
        if penalty>=4 and len(selected)<limit-1: continue
        entity=(e.primary_entities or ["unknown"])[0]
        if entities.get(entity,0)>=max_per_entity and e.relevance_score < 90: continue
        selected.append(e); counts[primary]=penalty+1
        entities[entity]=entities.get(entity,0)+1
        if len(selected)>=limit: break
    return selected

def payload(events, stats):
    return {"generated_at":iso(__import__('datetime').datetime.now(__import__('datetime').timezone.utc)),"statistics":stats,"items":[{"rank":i,"event_id":e.event_id,"title":e.representative_title,"categories":e.categories,"content_genre":e.content_genre,"newsworthiness_score":e.newsworthiness_score,"primary_entities":e.primary_entities,"relevance_score":e.relevance_score,"sources":sorted({a.source_name for a in e.articles}),"articles":[{"title":a.title,"url":a.url,"source":a.source_name,"publisher_id":a.publisher_id,"source_type":a.source_type,"source_tags":a.source_tags,"content_genre":a.content_genre,"source_language":a.language,"published_at":iso(a.published_at)} for a in e.articles]} for i,e in enumerate(events,1)]}

def write_outputs(events, stats, directory=None):
    directory = directory or ENGINE_OUTPUT
    path=Path(directory); path.mkdir(parents=True,exist_ok=True); data=payload(events,stats)
    (path/"briefing.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["NEWS ENGINE â€” DAILY BRIEFING",f"Generated: {data['generated_at']}",""]
    for item in data["items"]:
        lines += ["----------------------------------",f"#{item['rank']} â€” {item['title']}",f"Score: {item['relevance_score']}/100",f"Categoria: {', '.join(item['categories'])}",f"Fontes independentes: {len(item['sources'])}","","Fontes:"]+[f"- {s}" for s in sorted(set(item['sources']))]+["","Artigos:"]+[f"- {a['title']} â€” {a['url']}" for a in item['articles']]+[""]
    (path/"briefing.md").write_text("\n".join(lines),encoding="utf-8")

