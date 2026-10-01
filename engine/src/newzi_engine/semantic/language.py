"""Small deterministic language contract for editorial output."""
import re

PT_MARKERS={" de "," da "," do "," que "," para "," uma "," os "," as "," notícia", " empresa", " governo", " saúde", " não "}
EN_MARKERS={" the "," and "," of "," to "," for "," a "," an "," news", " company", " government", " health", " is "}

def detect_text_language(text, declared=None):
    declared=(declared or "").lower()
    if declared.startswith("pt"): return "pt-BR"
    value=" "+re.sub(r"\s+", " ", str(text or "").casefold())+" "
    pt=sum(value.count(marker) for marker in PT_MARKERS)+sum(value.count(ch) for ch in "ãõçáéíóúâêô")
    en=sum(value.count(marker) for marker in EN_MARKERS)
    if pt==0 and en==0: return "unknown"
    return "pt-BR" if pt>=max(2,en) else "en"

def language_gate(value, output_language):
    if output_language != "pt-BR": return "PASS"
    text=" ".join(str(value.get(key) or "") for key in ("headline","summary","why_it_matters"))
    return "PASS" if detect_text_language(text)=="pt-BR" else "FAIL"

