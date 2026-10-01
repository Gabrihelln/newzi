"""Deterministic semantic-output validation and grounding checks."""
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from .schemas import EVENT_TYPES, validate_classifier, validate_verifier

ABSTAIN_REASONS = {"INSUFFICIENT_EVIDENCE", "AMBIGUOUS_EVENT", "ENTITY_UNCLEAR", "CONTENT_TYPE_UNCLEAR", "CONFLICTING_EVIDENCE"}

def norm(value: str | None) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    return " ".join(value.casefold().strip().split())

def evidence_text(event: dict[str, Any]) -> str:
    parts = [event.get("representative_title", ""), event.get("title", ""), event.get("description", ""), json_text(event.get("fingerprint", {}))]
    for article in event.get("articles", []):
        parts += [article.get("title", ""), article.get("description", ""), json_text(article.get("fingerprint", {}))]
    return norm(" ".join(str(x) for x in parts if x is not None))

def json_text(value: Any) -> str:
    if isinstance(value, dict): return " ".join(f"{k} {json_text(v)}" for k, v in value.items())
    if isinstance(value, list): return " ".join(json_text(v) for v in value)
    return str(value)

@dataclass
class SemanticValidation:
    status: str
    result: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)

class SemanticOutputValidator:
    """Strict, deterministic validator. It never calls an LLM and never fills fields."""
    def __init__(self, strict=True): self.strict = strict

    def validate_classifier(self, text: str, event: dict[str, Any], max_evidence: int = 20) -> SemanticValidation:
        try: raw = validate_classifier(text, max_evidence)
        except Exception as exc: return SemanticValidation("INVALID", errors=[str(exc)], codes=["INVALID_OUTPUT"])
        errors: list[str] = []; codes: list[str] = []
        # New contract: decision is mandatory. Legacy compatibility is explicit and only used by old callers.
        if "decision" not in raw:
            if self.strict: errors.append("missing decision"); codes.append("INVALID_OUTPUT")
            else: raw["decision"] = "CLASSIFIED"
        if "abstain_reason" in raw and raw["abstain_reason"] is not None and raw["abstain_reason"] not in ABSTAIN_REASONS:
            errors.append("invalid abstain_reason"); codes.append("INVALID_OUTPUT")
        decision = raw.get("decision", "CLASSIFIED")
        if decision not in {"CLASSIFIED", "ABSTAIN"}: errors.append("invalid decision"); codes.append("INVALID_OUTPUT")
        if decision == "ABSTAIN":
            if raw.get("abstain_reason") not in ABSTAIN_REASONS: errors.append("ABSTAIN requires abstain_reason"); codes.append("INVALID_OUTPUT")
        else:
            if not raw.get("event_subject", "").strip(): errors.append("empty event_subject"); codes.append("EMPTY_SEMANTIC_OUTPUT")
            if not raw.get("reasoning_summary", "").strip(): errors.append("empty reasoning_summary"); codes.append("EMPTY_SEMANTIC_OUTPUT")
            if not raw.get("core_factual_claim", "").strip(): errors.append("empty core_factual_claim"); codes.append("EMPTY_SEMANTIC_OUTPUT")
        if not isinstance(raw.get("newsworthiness"), int) or isinstance(raw.get("newsworthiness"), bool): errors.append("newsworthiness must be integer 0-100"); codes.append("INVALID_OUTPUT")
        if raw.get("confidence") == 1.0: codes.append("DEFAULT_LIKE_CONFIDENCE")
        text_evidence = evidence_text(event)
        entity = raw.get("main_entity")
        if entity and norm(entity) not in text_evidence:
            errors.append("main_entity not grounded"); codes.append("ENTITY_NOT_GROUNDED")
        claim = raw.get("core_factual_claim", "")
        if claim and decision == "CLASSIFIED":
            source_numbers = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", text_evidence))
            claim_numbers = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", norm(claim)))
            if claim_numbers - source_numbers: errors.append("claim contains unsupported number"); codes.append("CLAIM_NUMBER_CONFLICT")
        flags = {k: raw.get(k) for k in ("is_news_event", "is_analysis", "is_opinion", "is_promotional", "is_evergreen")}
        if raw.get("event_type") == "ANALYSIS" and not flags["is_analysis"]: errors.append("ANALYSIS requires is_analysis"); codes.append("EVENT_TYPE_INCOHERENT")
        if raw.get("event_type") == "OPINION" and not flags["is_opinion"]: errors.append("OPINION requires is_opinion"); codes.append("EVENT_TYPE_INCOHERENT")
        if raw.get("event_type") in {"BUYING_GUIDE", "HOW_TO", "REVIEW", "EVERGREEN"} and flags["is_news_event"]: errors.append("evergreen/content type cannot be breaking news"); codes.append("EVENT_TYPE_INCOHERENT")
        funding_words = ("fund", "funding", "investment", "series", "raised", "capital")
        if raw.get("event_type") == "FUNDING" and not any(w in text_evidence for w in funding_words): errors.append("funding lacks funding evidence"); codes.append("EVENT_TYPE_INCOHERENT")
        if errors: return SemanticValidation("INVALID", raw, errors, sorted(set(codes)))
        return SemanticValidation("ABSTAINED" if decision == "ABSTAIN" else "VALID", raw, [], sorted(set(codes)))

    def validate_verifier(self, text: str, left: dict[str, Any], right: dict[str, Any], max_evidence: int = 10) -> SemanticValidation:
        try: raw = validate_verifier(text, max_evidence)
        except Exception as exc: return SemanticValidation("INVALID", errors=[str(exc)], codes=["INVALID_OUTPUT"])
        errors=[]; codes=[]
        if raw["decision"] == "SAME_EVENT" and not raw["same_event"]: errors.append("same_event mismatch"); codes.append("INVALID_OUTPUT")
        if raw["decision"] != "SAME_EVENT" and raw["same_event"]: errors.append("same_event mismatch"); codes.append("INVALID_OUTPUT")
        if not raw["reason"].strip(): errors.append("empty reason"); codes.append("EMPTY_SEMANTIC_OUTPUT")
        if errors: return SemanticValidation("INVALID", raw, errors, sorted(set(codes)))
        return SemanticValidation("VALID", raw, [], [])

