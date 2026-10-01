from collections import OrderedDict
from ..utils.text import normalize_title

def exact_deduplicate(articles):
    seen_id=set(); seen_url=set(); seen_title=set(); out=[]; removed=[]
    for a in articles:
        key=(a.article_id,a.canonical_url,normalize_title(a.title))
        if a.article_id in seen_id or a.canonical_url in seen_url or normalize_title(a.title) in seen_title:
            removed.append(a); continue
        seen_id.add(a.article_id); seen_url.add(a.canonical_url); seen_title.add(normalize_title(a.title)); out.append(a)
    return out, removed

