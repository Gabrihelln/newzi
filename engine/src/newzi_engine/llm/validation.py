import json, re
SCHEMA_VERSION = "semantic_probe_v1_schema_v1"
REQUIRED = {"main_entity": str, "event_type": str, "factuality": str, "is_news_event": bool, "is_evergreen": bool, "confidence": (int, float), "reason": str}
def parse_json_object(text: str) -> dict:
    value=re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I|re.S).strip()
    try: parsed=json.loads(value)
    except json.JSONDecodeError:
        match=re.search(r"\{.*\}", value, flags=re.S)
        if not match: raise ValueError("structured output is not JSON")
        try: parsed=json.loads(match.group(0))
        except json.JSONDecodeError as exc: raise ValueError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(parsed, dict): raise ValueError("structured output must be an object")
    return parsed

def extract_json(text: str) -> dict:
    parsed=parse_json_object(text)
    for key,typ in REQUIRED.items():
        if key not in parsed: raise ValueError(f"missing field: {key}")
        if not isinstance(parsed[key], typ) or (key=="confidence" and not 0 <= float(parsed[key]) <= 1): raise ValueError(f"invalid type/value for field: {key}")
    return {"main_entity":parsed["main_entity"].strip(),"event_type":parsed["event_type"].strip(),"factuality":parsed["factuality"].strip(),"is_news_event":parsed["is_news_event"],"is_evergreen":parsed["is_evergreen"],"confidence":float(parsed["confidence"]),"reason":parsed["reason"].strip()}

