import re
from ..llm.validation import parse_json_object

EVENT_TYPES={"BREAKING_NEWS","NEWS_EVENT","PRODUCT_ANNOUNCEMENT","COMPANY_ANNOUNCEMENT","FUNDING","ACQUISITION","REGULATION","LEGAL","RESEARCH","ANALYSIS","OPINION","INTERVIEW","PROMOTION","EVENT_PROMOTION","ROUNDUP","BUYING_GUIDE","HOW_TO","REVIEW","EVERGREEN","OTHER"}
def validate_classifier(text, max_evidence=20):
    raw=parse_json_object(text)
    required={"main_entity","secondary_entities","event_subject","event_type","is_news_event","is_evergreen","is_analysis","is_opinion","is_promotional","topic_categories","newsworthiness","confidence","reasoning_summary","core_factual_claim","evidence_indices"}
    missing=required-set(raw)
    if missing: raise ValueError("missing fields: "+", ".join(sorted(missing)))
    if raw["main_entity"] is not None and not isinstance(raw["main_entity"],str): raise ValueError("main_entity must be string or null")
    if not isinstance(raw["secondary_entities"],list) or not all(isinstance(x,str) for x in raw["secondary_entities"]): raise ValueError("secondary_entities must be string list")
    if raw["event_type"] not in EVENT_TYPES: raise ValueError("invalid event_type")
    for key in ("is_news_event","is_evergreen","is_analysis","is_opinion","is_promotional"):
        if not isinstance(raw[key],bool): raise ValueError(f"{key} must be boolean")
    if "deterministic_classification_agreement" in raw and not isinstance(raw["deterministic_classification_agreement"],bool): raise ValueError("deterministic_classification_agreement must be boolean")
    if not isinstance(raw["topic_categories"],list) or not all(isinstance(x,str) for x in raw["topic_categories"]): raise ValueError("topic_categories must be list")
    if not isinstance(raw["newsworthiness"],(int,float)) or not 0 <= float(raw["newsworthiness"]) <= 100: raise ValueError("newsworthiness outside 0-100")
    if not isinstance(raw["confidence"],(int,float)) or not 0 <= float(raw["confidence"]) <= 1: raise ValueError("confidence outside 0-1")
    if not isinstance(raw["core_factual_claim"],str): raise ValueError("core_factual_claim must be string")
    if not isinstance(raw["evidence_indices"],list) or not all(isinstance(x,int) and 0 <= x < max_evidence for x in raw["evidence_indices"]): raise ValueError("invalid evidence_indices")
    return raw

def validate_verifier(text, max_evidence=10):
    raw=parse_json_object(text); required={"decision","same_event","confidence","shared_event","reason","evidence_indices"}; missing=required-set(raw)
    if missing: raise ValueError("missing fields: "+", ".join(sorted(missing)))
    if raw["decision"] not in {"SAME_EVENT","DIFFERENT_EVENT","UNCERTAIN"}: raise ValueError("invalid decision")
    if not isinstance(raw["same_event"],bool): raise ValueError("same_event must be boolean")
    if not isinstance(raw["confidence"],(int,float)) or not 0 <= float(raw["confidence"]) <= 1: raise ValueError("confidence outside 0-1")
    if not isinstance(raw["shared_event"],str) or not isinstance(raw["reason"],str): raise ValueError("text fields invalid")
    if not isinstance(raw["evidence_indices"],list) or not all(isinstance(x,int) and 0 <= x < max_evidence for x in raw["evidence_indices"]): raise ValueError("invalid evidence_indices")
    return raw

