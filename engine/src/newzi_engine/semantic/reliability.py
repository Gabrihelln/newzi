"""External reliability scoring and gate; independent from LLM self-confidence."""
from dataclasses import dataclass
from .validator import evidence_text, norm

@dataclass
class ReliabilityWeights:
    semantic_validation: float = .20
    evidence_completeness: float = .15
    entity_grounding: float = .15
    claim_grounding: float = .15
    deterministic_agreement: float = .10
    consistency: float = .10
    coherence: float = .10
    model_confidence: float = .05

@dataclass
class ReliabilityDecision:
    score: float
    gate: str
    components: dict[str, float]
    reasons: list[str]

def deterministic_agreement(semantic: dict, deterministic: dict | None):
    """Compare semantic fields with supplied F1 output; never trusts an LLM-produced flag."""
    if not deterministic: return None
    checks=[]
    genre=deterministic.get("content_genre") or deterministic.get("genre")
    if genre and semantic.get("event_type"): checks.append(norm(genre) == norm(semantic["event_type"]))
    for key in ("is_analysis", "is_opinion", "is_promotional", "is_evergreen"):
        if key in deterministic and key in semantic: checks.append(bool(deterministic[key]) == bool(semantic[key]))
    return all(checks) if checks else None

def semantic_reliability_score(result, validation_status="VALID", validation_codes=None, event=None, deterministic=None, consistency=1.0, weights=None):
    weights = weights or ReliabilityWeights(); codes=set(validation_codes or []); event=event or {}; result=result or {}
    evidence = 1.0 if result.get("evidence_indices") else 0.0
    entity = result.get("main_entity")
    grounded = 1.0 if not entity or norm(entity) in evidence_text(event) else 0.0
    claim = 1.0 if result.get("core_factual_claim", "").strip() else 0.0
    validation = 1.0 if validation_status == "VALID" else 0.0
    coherence = 0.0 if "EVENT_TYPE_INCOHERENT" in codes else 1.0
    claim_grounding = 0.0 if any(x in codes for x in {"CLAIM_NUMBER_CONFLICT", "CLAIM_NOT_GROUNDED"}) else claim
    agreement = 1.0 if deterministic is True else (0.5 if deterministic is None else 0.0)
    model_conf = min(1.0, max(0.0, float(result.get("confidence", 0.0))))
    values={"semantic_validation":validation,"evidence_completeness":evidence,"entity_grounding":grounded,"claim_grounding":claim_grounding,"deterministic_agreement":agreement,"consistency":max(0.0,min(1.0,consistency)),"coherence":coherence,"model_confidence":model_conf}
    score=sum(values[k]*getattr(weights,k) for k in values)
    return round(score, 4), values

def reliability_gate(score, validation_status, codes=None, high_threshold=.82, review_threshold=.60, hard_requirements=None):
    codes=set(codes or [])
    if validation_status == "INVALID" or "ENTITY_NOT_GROUNDED" in codes or "CLAIM_NUMBER_CONFLICT" in codes: return "REJECT"
    if validation_status == "ABSTAINED": return "ABSTAIN"
    if hard_requirements:
        failed=[name for name,ok in hard_requirements.items() if not ok]
        if failed: return "REVIEW" if all(name not in {"grounded","semantic_valid"} for name in failed) else "REJECT"
    if score >= high_threshold: return "TRUSTED_SHADOW"
    if score >= review_threshold: return "REVIEW"
    return "ABSTAIN"

