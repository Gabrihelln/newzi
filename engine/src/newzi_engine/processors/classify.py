CLASSIFIER_VERSION = "topic-classifier-v3"
import re
from functools import lru_cache
from ..utils.text import normalize_title
from ..topic_registry import taxonomy

def classification_terms():
    return {node_id: node.get("terms", {}) for node_id, node in taxonomy().nodes.items() if node.get("active", True)}


@lru_cache(maxsize=4)
def _compiled_terms(signature):
    """Compile taxonomy matching patterns once per taxonomy content version."""
    compiled = []
    for category, terms in signature:
        by_first_word = {}
        for term, weight in terms:
            first_word = re.search(r"[a-z0-9]+", term.casefold())
            if first_word:
                by_first_word.setdefault(first_word.group(0), []).append((re.compile(r"\b" + re.escape(term) + r"\b"), weight))
        compiled.append((category, {word: tuple(items) for word, items in by_first_word.items()}))
    return tuple(compiled)


def _compiled_classification_terms():
    terms = classification_terms()
    signature = tuple(
        (category, tuple(sorted((str(term), weight) for term, weight in category_terms.items())))
        for category, category_terms in sorted(terms.items())
    )
    return _compiled_terms(signature)


_CONFLICT_CUES = re.compile(r"\b(missile|missiles|airstrike|airstrikes|bombed|bombing|bombardment|shelling|war|warfare|armed conflict|military strike|air raid|invasion|invaded|ceasefire|guerra|conflito armado|forcas armadas|ataque aereo|ataque militar|bombardeio|bombardeado|bombardeada|bombas|invasao|cessar fogo)\b")
_ATTACK_CUE = re.compile(r"\b(attack|attacked|attacks|ataque|atacou|atacada|atacado)\b")
_COMBAT_CUE = re.compile(r"\b(combat|combatting|combate|combater)\b")
_MILITARY_CONTEXT = re.compile(r"\b(military|armed forces|troops|soldiers|weapons|armed group|militar|forcas armadas|tropas|soldados|armas|grupo armado)\b")
_EDUCATION_ACTION = re.compile(r"\b(curriculum|curricula|education policy|school board|teacher|teachers|classroom|exam|university research|campus research|enrollment|scholarship|new school|school system|minister of education|curriculo|professor|professores|sala de aula|prova|pesquisa universitaria|matricula|bolsa de estudo|secretaria de educacao|ministerio da educacao)\b")
_HEALTH_ACTION = re.compile(r"\b(treatment|cancer|clinical trial|vaccine|vaccination|diagnosis|medicine|drug trial|patients|public health|healthcare|therapy|surgeon|treatment|tratamento|cancer|ensaio clinico|vacina|vacinacao|diagnostico|medicamento|pacientes|saude publica|terapia|cirurgia)\b")
_SPORTS_CONTEXT = re.compile(r"\b(football|soccer|tennis|basketball|court|match|tournament|league|goal|futebol|tenis|basquete|quadra|partida|torneio|campeonato|gol)\b")
_GEOGRAPHIC_BANK = re.compile(r"\b(west bank|river bank|blood bank)\b")
_CRIME_CONTEXT = re.compile(r"\b(arrested|arrest|charged|charges|convicted|conviction|sentenced|indicted|assault|battery|domestic violence|preso|presa|prisao|acusado|acusada|condenado|condenada|agressao|violencia domestica)\b")
_DEVICE_CONTEXT = re.compile(r"\b(device|smartphone|phone|laptop|computer|electric|lithium|charging|charger|eletronico|aparelho|celular|computador|carregamento|carregador|bateria de)\b")
_LEGAL_ACTION = re.compile(r"\b(court rules|court orders|judge|judges|lawsuit|ruling|verdict|prosecutor|indicted|sentence|legal case|tribunal decide|juiz|juiza|processo judicial|sentenca|condenacao|promotor|recurso judicial|convicted|conviction|court|law|legal|trial|appeal|sentenced|condenado|condenada|lei|julgamento|tribunal)\b")
_LEGAL_RULING = re.compile(r"\b(court rules|court orders|judge|judges|lawsuit|ruling|verdict|prosecutor|indicted|convicted|conviction|sentenced|legal case|tribunal decide|juiz|juiza|processo judicial|sentenca|condenacao|promotor|recurso judicial|julgamento)\b")


def classify_article(article):
    title_text = normalize_title(article.title)
    description_text = normalize_title(article.description)
    terms_by_category = _compiled_classification_terms()
    scores = {category: 0.0 for category, _ in terms_by_category}
    title_words = set(re.findall(r"[a-z0-9]+", title_text))
    description_words = set(re.findall(r"[a-z0-9]+", description_text))
    # Check each taxonomy term once per field. The old token loop added the same
    # title hit once for every repeated token in the description.
    for category, by_first_word in terms_by_category:
        seen = set()
        for word in title_words | description_words:
            for pattern, weight in by_first_word.get(word, ()):
                if pattern.pattern in seen:
                    continue
                seen.add(pattern.pattern)
                in_title = bool(pattern.search(title_text))
                in_description = bool(pattern.search(description_text))
                if in_title:
                    scores[category] += weight * 2.2
                if in_description:
                    scores[category] += weight * 0.55
    meaningful_tags = " ".join(normalize_title(tag) for tag in article.source_tags if normalize_title(tag) != "other")
    if meaningful_tags:
        tag_words = set(re.findall(r"[a-z0-9]+", meaningful_tags))
        for category, by_first_word in terms_by_category:
            seen = set()
            for word in tag_words:
                for pattern, weight in by_first_word.get(word, ()):
                    if pattern.pattern in seen:
                        continue
                    seen.add(pattern.pattern)
                    if pattern.search(meaningful_tags):
                        scores[category] += max(0.5, weight * 0.2)
    combined = f"{title_text} {description_text}"
    military_context = bool(_MILITARY_CONTEXT.search(combined))
    title_conflict_signal = bool(_CONFLICT_CUES.search(title_text))
    title_party_context = bool(re.search(r"\b(ukraine|kyiv|gaza|israel|iran|russia|russian|putin|hamas|hezbollah|syria|sudan|taiwan|nato|ucrania|ira|russia)\b", title_text))
    description_conflict_signal = bool(_CONFLICT_CUES.search(description_text))
    conflict_match = title_conflict_signal or (title_party_context and description_conflict_signal) or (military_context and bool(_ATTACK_CUE.search(combined) or _COMBAT_CUE.search(combined)))
    if conflict_match:
        for category, bonus in (("CONFLITOS_INTERNACIONAIS", 32), ("GEOPOLITICA", 16), ("WORLD", 8), ("DEFESA", 7)):
            if category in scores:
                scores[category] += bonus
        if not _EDUCATION_ACTION.search(combined):
            scores["EDUCATION"] = scores.get("EDUCATION", 0) * 0.12
        if not _HEALTH_ACTION.search(combined):
            scores["HEALTH"] = scores.get("HEALTH", 0) * 0.12
    elif military_context and "DEFESA" in scores:
        scores["DEFESA"] += 10
        if "GEOPOLITICA" in scores:
            scores["GEOPOLITICA"] += 3
    if _GEOGRAPHIC_BANK.search(combined) and not re.search(r"\b(central bank|interest rate|loan|lending|deposit|credit|financial|banco central|juros|emprestimo|credito|deposito)\b", combined):
        scores["FINANCE"] = scores.get("FINANCE", 0) * 0.12
    if not conflict_match and _LEGAL_ACTION.search(title_text):
        scores["DEFESA"] = scores.get("DEFESA", 0) * 0.15
    if _CRIME_CONTEXT.search(title_text) and not _DEVICE_CONTEXT.search(combined):
        for category in ("TECHNOLOGY", "HARDWARE"):
            if category in scores:
                scores[category] *= 0.12
    if not conflict_match and _SPORTS_CONTEXT.search(combined) and not _LEGAL_RULING.search(combined):
        for category in scores:
            if category.startswith("JUSTICA") or category == "JUSTICE":
                scores[category] *= 0.2
    best = max(scores.values(), default=0)
    selected = {category for category, score in scores.items() if score >= 4 and score >= best * 0.45} if best else set()
    for category in tuple(selected):
        selected.update(taxonomy().ancestors(category))
    article.categories = sorted(selected) if selected else ["OTHER"]
    return article, scores

def classify_articles(articles):
    for article in articles: classify_article(article)
    return articles

def classify_text(title, description="", source_tags=None):
    class Obj: pass
    obj=Obj(); obj.title=title; obj.description=description; obj.source_tags=source_tags or []; obj.categories=[]
    return classify_article(obj)[0].categories

