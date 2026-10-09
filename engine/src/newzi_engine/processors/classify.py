CLASSIFIER_VERSION = "topic-classifier-v4"
import re
from functools import lru_cache
from ..utils.text import normalize_title
from ..topic_registry import taxonomy

# Below this confidence the strongest topic is not trusted; the story is filed under a
# broad, safe domain (World for international/conflict news, else the source's domain).
MIN_CLASSIFICATION_CONFIDENCE = 0.35
MIN_TAG_SCORE = 4.0
RELATIVE_TAG_SCORE = 0.4
FALLBACK_TAG_SCORE = 4.0

def classification_terms():
    return {node_id: node.get("terms", {}) for node_id, node in taxonomy().nodes.items() if node.get("active", True)}


@lru_cache(maxsize=4)
def _compiled_terms(signature):
    """Compile taxonomy matching patterns once per taxonomy content version.

    Terms are normalized exactly like the article text (accents and punctuation
    removed), so "inflação" and "e-commerce" match "inflacao" and "e commerce".
    """
    compiled = []
    for category, terms in signature:
        by_first_word = {}
        seen = set()
        for term, weight in terms:
            normalized = normalize_title(term)
            first_word = re.search(r"[a-z0-9]+", normalized)
            if not first_word or normalized in seen:
                continue
            seen.add(normalized)
            by_first_word.setdefault(first_word.group(0), []).append((re.compile(r"\b" + re.escape(normalized) + r"\b"), weight))
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
# Vocabulary of war/defense coverage. Unambiguous words always guard; ambiguous
# ones ("ataque", "defesa", "conflito") guard unless the story is clearly about
# sport, cyber security or health ("ataque cardíaco", "defesa do time").
_CONFLICT_GUARD_STRONG = re.compile(r"\b(guerra|guerras|missil|misseis|invasao|invadiu|invadido|exercito|exercitos|tropas|bombardeio|bombardeios|bombardeado|militar|militares|forcas armadas|cessar fogo|war|wars|warfare|missile|missiles|invasion|invaded|army|armies|troops|military|airstrike|airstrikes|air strike|drone strike|shelling|bombing|bombardment|ceasefire|armed forces)\b")
_CONFLICT_GUARD_AMBIGUOUS = re.compile(r"\b(ataque|ataques|atacou|atacado|atacada|defesa|conflito|conflitos|attack|attacks|attacked|defense|defence|conflict|conflicts)\b")
_NON_MILITARY_CONTEXT = re.compile(r"\b(hacker|hackers|ciberataque|cyberattack|cyber|ransomware|phishing|cardiaco|cardiac|heart attack|panico|panic|asma|asthma|tecnico|tecnica|zagueiro|goleiro|defender|goalkeeper|striker|atacante|meia|torcida|campeonato|partida|match|tournament|torneio|placar|escalacao|tese|advogado|advogada|defensoria|consumidor)\b")
# Evidence that a war-related story really is about education/culture/entertainment.
_CULTURE_ACTION = re.compile(r"\b(exhibition|exposicao|museum exhibit|festival|film festival|premiere|estreia|album|concert|concerto|show de|book launch|lancamento do livro|novel|romance|box office|bilheteria|oscar|emmy|grammy|series finale|documentary|documentario|peca teatral|bienal|curadoria|curator)\b")
_GUARDED_DOMAINS = ("EDUCATION", "CULTURE", "ENTERTAINMENT")


def _conflict_guard(title_text, description_text, combined):
    if _CONFLICT_GUARD_STRONG.search(combined):
        return True
    return bool(_CONFLICT_GUARD_AMBIGUOUS.search(title_text)) and not _NON_MILITARY_CONTEXT.search(combined) and not _SPORTS_CONTEXT.search(combined)


def _suppress_guarded_domains(scores, title_text, combined):
    """War coverage that merely mentions a school, museum or film is not Education/Culture/Entertainment."""
    registry = taxonomy()
    for domain in _GUARDED_DOMAINS:
        if domain not in registry.nodes:
            continue
        subtree = (domain, *registry.descendants(domain))
        evidence = _EDUCATION_ACTION.search(title_text) if domain == "EDUCATION" else _CULTURE_ACTION.search(title_text)
        if evidence:
            continue
        for node in subtree:
            if node in scores:
                scores[node] *= 0.1


_LEGAL_RULING = re.compile(r"\b(court rules|court orders|judge|judges|lawsuit|ruling|verdict|prosecutor|indicted|convicted|conviction|sentenced|legal case|tribunal decide|juiz|juiza|processo judicial|sentenca|condenacao|promotor|recurso judicial|julgamento)\b")


_NON_MILITARY_IDIOMS = (
    (re.compile(r"\bculture wars?\b"), "culture debate"), (re.compile(r"\bguerras? culturais?\b"), "debate cultural"),
    (re.compile(r"\btrade wars?\b"), "trade dispute"), (re.compile(r"\bguerras? comerciais?\b|\bguerra comercial\b"), "disputa comercial"),
    (re.compile(r"\bguerras? tarifarias?\b"), "disputa tarifaria"), (re.compile(r"\bguerra fiscal\b"), "disputa fiscal"),
    (re.compile(r"\bprice wars?\b"), "price competition"), (re.compile(r"\bguerra de precos\b"), "competicao de precos"),
    (re.compile(r"\b(console|streaming|browser|talent|bidding|chip|subscription) wars?\b"), r"\1 competition"),
    (re.compile(r"\bstar wars\b"), "starwars"), (re.compile(r"\bwar on drugs\b"), "drug policy"),
    (re.compile(r"\b(gears|god|art|days|tides|ashes) of war\b"), r"\1ofwar game"), (re.compile(r"\bwar thunder\b"), "warthunder game"),
    (re.compile(r"\bthis war of mine\b"), "thiswarofmine game"), (re.compile(r"\bwar of the worlds\b"), "waroftheworlds"),
    (re.compile(r"\bguerra as drogas\b"), "politica de drogas"),
)


_GAME_CONTEXT = re.compile(r"\b(xbox|playstation|ps5|ps4|nintendo|steam|videogame|videogames|video game|video games|game|games|gameplay|dlc|jogo|jogos|gamer|gamers|franquia|remaster|remake|expansao)\b")
_REAL_WAR_SIGNAL = re.compile(r"\b(missil|misseis|missile|missiles|tropas|troops|invasao|invasion|exercito|army|bombardeio|bombing|airstrike|ceasefire|cessar fogo|soldados|soldiers|gaza|ukraine|ucrania|israel|russia|hamas|hezbollah|sudan|nato|otan|pentagon|pentagono)\b")


def _strip_non_military_language(raw, normalized, context=""):
    """Remove idioms and surnames that look like war vocabulary ("culture war", "Ruy Guerra").

    In video-game coverage, "war"/"guerra" without any real military signal is a title word.
    """
    for pattern, replacement in _NON_MILITARY_IDIOMS:
        normalized = pattern.sub(replacement, normalized)
    probe = f"{normalized} {context}"
    if _GAME_CONTEXT.search(probe) and not _REAL_WAR_SIGNAL.search(probe):
        normalized = re.sub(r"\b(war|wars|warfare|guerra|guerras)\b", "game", normalized)
    for match in re.finditer(r"\b[A-ZÀ-Ý][a-zà-ÿ]+\s+(?:Guerra|Guerras)\b", raw or ""):
        phrase = normalize_title(match.group(0))
        normalized = re.sub(r"\b" + re.escape(phrase) + r"\b", phrase.rsplit(" ", 1)[0], normalized)
    return normalized


def classify_article(article):
    raw_title, raw_description = normalize_title(article.title), normalize_title(article.description)
    title_text = _strip_non_military_language(article.title, raw_title, raw_description)
    description_text = _strip_non_military_language(article.description, raw_description, raw_title)
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
    # "ira" is not listed: without accents it is also the verb "irá".
    title_party_context = bool(re.search(r"\b(ukraine|kyiv|kiev|gaza|israel|iran|teera|russia|russian|putin|hamas|hezbollah|syria|siria|sudan|taiwan|nato|otan|ucrania|russia)\b", title_text))
    description_conflict_signal = bool(_CONFLICT_CUES.search(description_text))
    conflict_match = title_conflict_signal or (title_party_context and description_conflict_signal) or (military_context and bool(_ATTACK_CUE.search(combined) or _COMBAT_CUE.search(combined)))
    # A film, exhibition or school policy *about* a war is a cultural/education story.
    about_artwork_or_education = bool(_CULTURE_ACTION.search(title_text) or _EDUCATION_ACTION.search(title_text))
    if conflict_match and not about_artwork_or_education:
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
    if conflict_match or _conflict_guard(title_text, description_text, combined):
        _suppress_guarded_domains(scores, title_text, combined)
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


_GEOGRAPHIC_CONTEXT = frozenset({"BRAZIL", "REGIOES_DO_BRASIL", "ESTADOS", "CIDADES", "AMERICA_LATINA", "ESTADOS_UNIDOS",
                                 "EUROPA", "ASIA", "AFRICA", "ORIENTE_MEDIO", "UNIAO_EUROPEIA"})
_INTERNATIONAL_CONTEXT = re.compile(r"\b(international|internacional|united nations|onu|un security council|diplomat|diplomats|diplomacia|diplomacy|embassy|embaixada|foreign minister|chanceler|chancelaria|summit|cupula|sanctions|sancoes|refugees|refugiados)\b")


def classification_confidence(scores, best_id):
    """0..1 trust in the strongest topic: absolute strength plus margin over unrelated topics.

    Ancestors and descendants of the best topic are agreement, not competition.
    """
    best = scores.get(best_id, 0)
    if best <= 0:
        return 0.0
    registry = taxonomy()
    lineage = {best_id, *registry.ancestors(best_id), *registry.descendants(best_id)}
    # Places only compete with other places; they are context for thematic topics.
    ignored = set() if best_id in _GEOGRAPHIC_CONTEXT else _GEOGRAPHIC_CONTEXT
    rival = max((score for node, score in scores.items() if node not in lineage and node not in ignored), default=0)
    strength = min(1.0, best / 16.0)
    margin = max(0.0, (best - rival) / best)
    return round(0.65 * strength + 0.35 * margin, 3)


def classify_for_index(article, source_categories=()):
    """Tags, primary topic and confidence used by the product index.

    Keeps only tags close to the strongest topic (incidental mentions are dropped)
    and, when the strongest topic is not trustworthy, files the story under World
    (international/conflict coverage) or the source's own domain instead of guessing.
    """
    registry = taxonomy()
    _, raw_scores = classify_article(article)
    scores = {node: float(score) for node, score in raw_scores.items() if score > 0 and registry.resolve(node)}
    best_id = max(scores, key=lambda node: (scores[node], -len(registry.ancestors(node)), node), default=None)
    # Places are context, not the subject: "Vasco é campeão ... no Rio de Janeiro" is sport.
    # When a geographic topic wins, a reasonably supported thematic topic leads instead.
    if best_id in _GEOGRAPHIC_CONTEXT:
        topical = max((node for node in scores if node not in _GEOGRAPHIC_CONTEXT), key=lambda node: scores[node], default=None)
        if topical and scores[topical] >= max(2.5, 0.5 * scores[best_id]):
            scores[topical] = max(scores[topical], MIN_TAG_SCORE, scores[best_id])
            best_id = topical
    best = scores.get(best_id, 0.0)
    confidence = classification_confidence(scores, best_id) if best_id else 0.0
    if best_id in _GEOGRAPHIC_CONTEXT:
        # A place name alone is weak evidence of what the story is about.
        confidence = round(confidence * 0.8, 3)
    tags = [(node, score) for node, score in scores.items() if score >= MIN_TAG_SCORE and score >= RELATIVE_TAG_SCORE * best]
    if tags and confidence >= MIN_CLASSIFICATION_CONFIDENCE:
        return {"tags": sorted(tags, key=lambda item: -item[1]), "primary": best_id, "confidence": confidence, "reason": "CLASSIFIED"}
    title_text, description_text = normalize_title(article.title), normalize_title(article.description)
    combined = (f"{_strip_non_military_language(article.title, title_text, description_text)} "
                f"{_strip_non_military_language(article.description, description_text, title_text)}")
    international =(_CONFLICT_GUARD_STRONG.search(combined) or _INTERNATIONAL_CONTEXT.search(combined)
                     or re.search(r"\b(ukraine|gaza|israel|iran|russia|putin|hamas|syria|sudan|taiwan|nato|otan|ucrania)\b", combined))
    fallback = "WORLD" if international and "WORLD" in registry.nodes else None
    if not fallback:
        fallback = next((registry.resolve(category) for category in source_categories if registry.resolve(category)), None)
    if not fallback and "WORLD" in registry.nodes:
        fallback = "WORLD"
    reason = "LOW_CONFIDENCE_FALLBACK" if tags else "NO_SIGNAL_FALLBACK"
    # Strong tags inside the fallback domain are still accurate and kept.
    kept = [(node, score) for node, score in tags if node == fallback or fallback in registry.ancestors(node)]
    if not any(node == fallback for node, _ in kept):
        kept.append((fallback, FALLBACK_TAG_SCORE))
    primary = max(kept, key=lambda item: item[1])[0]
    return {"tags": sorted(kept, key=lambda item: -item[1]), "primary": primary, "confidence": confidence, "reason": reason}

def classify_text(title, description="", source_tags=None):
    class Obj: pass
    obj=Obj(); obj.title=title; obj.description=description; obj.source_tags=source_tags or []; obj.categories=[]
    return classify_article(obj)[0].categories

