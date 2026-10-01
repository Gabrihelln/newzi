"""Hierarchical semantic classification and deterministic support signals."""
import json, re
from .validator import SemanticOutputValidator, SemanticValidation, evidence_text, norm
from newzi_engine.llm.validation import parse_json_object

CONTENT_FAMILIES={"NEWS","EDITORIAL","UTILITY","COMMERCIAL","UNKNOWN"}
FAMILY_TYPES={"NEWS":{"PRODUCT_ANNOUNCEMENT","COMPANY_ANNOUNCEMENT","FUNDING","ACQUISITION","REGULATION","LEGAL","RESEARCH","NEWS_EVENT"},"EDITORIAL":{"ANALYSIS","OPINION","INTERVIEW","REVIEW"},"UTILITY":{"BUYING_GUIDE","HOW_TO","ROUNDUP","EVERGREEN"},"COMMERCIAL":{"PROMOTION"},"UNKNOWN":{"OTHER"}}
SIGNALS={"FUNDING":("funding","funded","raised","raises","investment","investimento","financiamento","rodada","série","series"),"ACQUISITION":("acquire","acquisition","acquires","bought","compra","adquire","aquisição","merger","fusão"),"REGULATION":("law","regulation","rule","bill","policy","lei","regulação","regulamentação","regla","règle","politique"),"LEGAL":("court","lawsuit","sued","enforcement","judicial","processo","tribunal","demanda","demande","recall"),"RESEARCH":("study","research","paper","findings","estudo","pesquisa","investigación","étude","recherche"),"PRODUCT_ANNOUNCEMENT":("launch","launches","unveil","introduces","announces","release","api","modelo","lança","apresenta","anuncia","lanzamiento","annonce","nouveau modèle"),"BUYING_GUIDE":("buying guide","best","worth buying","guia de compra","melhor","guía de compra","guide d'achat"),"HOW_TO":("how to","step by step","tutorial","como configurar","como fazer","cómo","comment activer","comment faire"),"PROMOTION":("sale","discount","coupon","promo","deal","% off","desconto","cupom","oferta","rebaja","solde","réduction")}

def support_signal(event, subtype):
    text=evidence_text(event); return any(norm(term) in text for term in SIGNALS.get(subtype,()))

def family_support(event, family):
    text=evidence_text(event)
    if family=="COMMERCIAL": return support_signal(event,"PROMOTION")
    if family=="NEWS": return bool(re.search(r"\b(announc|launch|rais|study|research|law|regulation|court|acqui|fund|anuncia|lança|étude|loi)\w*\b",text))
    if family=="EDITORIAL": return any(x in text for x in ("analysis","opinion","interview","review","análise","opinião","entrevista","avaliação"))
    if family=="UTILITY": return any(support_signal(event,t) for t in ("BUYING_GUIDE","HOW_TO")) or any(x in text for x in ("roundup","history","guia","guide","como","how to"))
    return False

def family_for_type(event_type): return next((f for f,types in FAMILY_TYPES.items() if event_type in types),"UNKNOWN")

def validate_hierarchical(text,event,max_evidence=20):
    try: raw=parse_json_object(text)
    except Exception as exc: return SemanticValidation("INVALID",errors=[str(exc)],codes=["INVALID_OUTPUT"])
    missing={"content_family","family_confidence","type_confidence"}-set(raw)
    if missing: return SemanticValidation("INVALID",errors=["missing fields: "+", ".join(sorted(missing))],codes=["INVALID_OUTPUT"])
    if raw.get("content_family") not in CONTENT_FAMILIES: return SemanticValidation("INVALID",errors=["invalid content_family"],codes=["INVALID_OUTPUT"])
    for key in ("family_confidence","type_confidence"):
        if not isinstance(raw.get(key),(int,float)) or not 0 <= float(raw[key]) <= 1: return SemanticValidation("INVALID",errors=[key+" outside 0-1"],codes=["INVALID_OUTPUT"])
    base=SemanticOutputValidator(strict=True).validate_classifier(text,event,max_evidence)
    if base.status=="INVALID": return base
    result=base.result; result.update({k:raw[k] for k in ("content_family","family_confidence","type_confidence")}); codes=list(base.codes); errors=list(base.errors); family=raw["content_family"]; event_type=raw.get("event_type")
    if event_type not in FAMILY_TYPES.get(family,set()): errors.append("family/subtype incompatible"); codes.append("FAMILY_SUBTYPE_INCOHERENT")
    if family in {"NEWS","COMMERCIAL"} and event_type=="OTHER": errors.append("unsupported subtype"); codes.append("UNSUPPORTED_EVENT_TYPE")
    if event_type not in {"NEWS_EVENT","OTHER"} and not support_signal(event,event_type): errors.append("subtype lacks textual support"); codes.append("SUBTYPE_UNSUPPORTED")
    if family!="UNKNOWN" and not family_support(event,family): errors.append("family lacks support"); codes.append("FAMILY_UNSUPPORTED")
    if family=="NEWS" and event_type=="NEWS_EVENT":
        specific=[t for t in FAMILY_TYPES["NEWS"] if t not in {"NEWS_EVENT","COMPANY_ANNOUNCEMENT","PRODUCT_ANNOUNCEMENT"} and support_signal(event,t)]
        if specific: errors.append("NEWS_EVENT used despite specific support"); codes.append("NEWS_FALLBACK_PREMATURE")
    if raw.get("decision")=="ABSTAIN": return SemanticValidation("ABSTAINED",result,errors,sorted(set(codes)))
    if errors: return SemanticValidation("INVALID",result,errors,sorted(set(codes)))
    return SemanticValidation("VALID",result,[],sorted(set(codes)))

class HierarchicalClassifier:
    prompt_version="hierarchical_classifier_v1"; schema_version="semantic_hierarchical_v1"
    def __init__(self,service): self.service=service
    def classify(self,event,use_cache=False,deterministic=None,consistency=1.0):
        prompt="""TASK: classify this article in one compact JSON response. First decide content_family, then choose the most specific supported event_type within that family. If family or subtype is not supported by evidence, use decision ABSTAIN. Never invent facts, entities, dates, numbers or claims. NEWS_EVENT is only the fallback for NEWS when no specific subtype is supported. Use input language as evidence and keep enum values in English. FAMILIES: NEWS factual new event; EDITORIAL analysis/opinion/interview/review; UTILITY how-to/buying guide/roundup/evergreen; COMMERCIAL promotion; UNKNOWN insufficient evidence. NEWS TYPES: PRODUCT_ANNOUNCEMENT, COMPANY_ANNOUNCEMENT, FUNDING, ACQUISITION, REGULATION, LEGAL, RESEARCH, NEWS_EVENT. EDITORIAL TYPES: ANALYSIS, OPINION, INTERVIEW, REVIEW. UTILITY TYPES: BUYING_GUIDE, HOW_TO, ROUNDUP, EVERGREEN. COMMERCIAL TYPE: PROMOTION. Keep reasoning_summary short. Output exactly this schema: {\"decision\":\"CLASSIFIED\",\"abstain_reason\":null,\"content_family\":\"NEWS\",\"family_confidence\":0.85,\"type_confidence\":0.80,\"main_entity\":null,\"secondary_entities\":[],\"event_subject\":\"short subject\",\"event_type\":\"NEWS_EVENT\",\"is_news_event\":true,\"is_evergreen\":false,\"is_analysis\":false,\"is_opinion\":false,\"is_promotional\":false,\"topic_categories\":[],\"newsworthiness\":50,\"confidence\":0.75,\"reasoning_summary\":\"short evidence tag\",\"core_factual_claim\":\"short grounded claim\",\"evidence_indices\":[0]} INPUT: """+json.dumps(event,ensure_ascii=False)
        result=self.service.call(event.get("event_id",""),prompt,self.prompt_version,self.schema_version,lambda text,_event,max_evidence: validate_hierarchical(text,event,max_evidence),len(event.get("articles",[])),use_cache,event,0.0,deterministic,consistency)
        if result.get("status") in {"accepted","cache_hit"}:
            value=result.get("result",{}); family=value.get("content_family"); subtype=value.get("event_type"); codes=set(result.get("validation_codes",[])); hard={"semantic_valid":result.get("semantic_status")=="VALID","grounded":"ENTITY_NOT_GROUNDED" not in codes,"coherent":"FAMILY_SUBTYPE_INCOHERENT" not in codes and "EVENT_TYPE_INCOHERENT" not in codes,"family_supported":family_support(event,family) if family!="UNKNOWN" else False,"subtype_supported":subtype=="NEWS_EVENT" or subtype=="OTHER" or support_signal(event,subtype),"no_critical_deterministic_disagreement":deterministic is not False}; result["hard_requirements"]=hard; result["reliability_gate"]=__import__("newzi_engine.semantic.reliability",fromlist=["reliability_gate"]).reliability_gate(result.get("semantic_reliability_score",0),result.get("semantic_status","INVALID"),codes,hard_requirements=hard)
        return result

