import re
from ..utils.text import normalize_title

GENRES = ("BREAKING_NEWS", "NEWS_EVENT", "PRODUCT_ANNOUNCEMENT", "COMPANY_ANNOUNCEMENT", "FUNDING", "REGULATION", "RESEARCH", "ANALYSIS", "OPINION", "INTERVIEW", "EVENT_PROMOTION", "PROMOTION", "ROUNDUP", "BUYING_GUIDE", "HOW_TO", "REVIEW", "DEAL_COUPON", "OTHER")
ELIGIBLE = {"BREAKING_NEWS", "NEWS_EVENT", "PRODUCT_ANNOUNCEMENT", "COMPANY_ANNOUNCEMENT", "FUNDING", "REGULATION", "RESEARCH", "ANALYSIS"}
EXCLUDED = {"EVENT_PROMOTION", "PROMOTION", "ROUNDUP", "BUYING_GUIDE", "HOW_TO", "REVIEW", "DEAL_COUPON", "INTERVIEW", "OPINION", "OTHER"}

def classify_genre(article):
    title_text = normalize_title(article.title)
    text = normalize_title(f"{article.title} {article.description} {article.url} {' '.join(article.source_tags)}")
    if re.search(r"promo code|coupon|discount|save \d+|\bdeal\b|buy now|offers?", title_text): genre="DEAL_COUPON"
    elif re.search(r"book (your|a)|register now|tickets?|deadline to exhibit|exhibit table|\d+ days? left.*(exhibit|book|table)|sign up", title_text): genre="EVENT_PROMOTION"
    elif re.search(r"\b(roundup|weekly roundup|monthly roundup|this week in|top stories)\b", title_text): genre="ROUNDUP"
    elif re.search(r"\b(best|buying guide|our favorite|top \d+|top .* features?)\b", title_text): genre="BUYING_GUIDE"
    elif re.search(r"how to|tutorial|step by step|can you use|\b\d+ ways?\b", title_text): genre="HOW_TO"
    elif re.search(r"\breview\b|hands-on|tested", title_text): genre="REVIEW"
    elif re.search(r"interview|conversation|discuss", title_text): genre="INTERVIEW"
    elif re.search(r"analysis|why |what.s at stake|explained|biggest issues|how one .* built", title_text): genre="ANALYSIS"
    elif re.search(r"opinion|editorial", title_text): genre="OPINION"
    elif re.search(r"funding|raises? \$?|investment round|million funding|series [a-f]", title_text): genre="FUNDING"
    elif re.search(r"regulation|regulator|lawmakers?|lawsuit|court|ban(?:s|ned)?|government", title_text): genre="REGULATION"
    elif re.search(r"study|research|findings|paper|survey", title_text): genre="RESEARCH"
    elif re.search(r"launch|launches|introduc|unveil|releases?|announc|available", title_text): genre="PRODUCT_ANNOUNCEMENT" if any(x in title_text for x in ("product", "model", "feature", "api", "iphone", "siri", "platform")) else "COMPANY_ANNOUNCEMENT"
    elif re.search(r"\b(earthquake|storm|fire|dies|election|attack|arrest|seizes?)\b", title_text): genre="BREAKING_NEWS"
    elif article.title.strip(): genre="NEWS_EVENT"
    else: genre="OTHER"
    article.content_genre=genre
    return article

def classify_editorial(articles):
    for article in articles: classify_genre(article)
    return articles

