"""Story threads: one ongoing story's coverage across outlets and days, for the briefing.

Clustering (newzi_engine.clustering) keeps events narrow on purpose, so the same story often
splits into several events ("Papa Leão XIV recebe alta após cirurgia" and "Papa recebe alta do
hospital depois de cirurgia"). A briefing must tell a story once, through its latest state, so it
groups events into threads: headlines sharing enough rare words, weighted by how rare each word is
among the stories being considered. Common words ("Lula", "governo") weigh little, so two different
election stories stay apart while every "Papa ... alta ... câncer" headline joins one thread.
"""
import math
import re
import unicodedata
from collections import Counter, defaultdict

# Share of a story's word weight two stories must have in common to be one story.
THREAD_SIMILARITY = 0.4
# A story joining a thread must loosely resemble the thread's first story...
ANCHOR_SIMILARITY = 0.25
# ...and, once the thread has SUPPORT_FROM stories, closely resemble MIN_SUPPORT of them, so one
# loosely related story cannot chain others into a big thread ("Papa recebe alta" -> "Papa fala com
# Putin" -> ...). An update ("recebe alta" after "celebra missa no hospital") resembles several.
MIN_SUPPORT = 2
SUPPORT_FROM = 3
# Two stories sharing fewer words are never one story, however rare the words.
MIN_SHARED_WORDS = 3
# One story is about the same someone or somewhere (Leão, Jottapê, Oregon): headline templates
# ("X x Y: onde assistir", "Atuações do X: dê suas notas") share words but never their names.
# The name must be uncommon: "EUA" or "Brasileirão" are in too many stories to prove anything.
MIN_SHARED_NAMES = 1
# Shared names (Lula, Flávio) say who a story is about, not what happened; two stories must also
# share this many uncommon words about the fact itself (cirurgia, câncer, pulmão).
MIN_SHARED_FACT_WORDS = 2
# A description sentence repeated by this many stories is an outlet's boilerplate, not evidence.
BOILERPLATE_REPEATS = 3
# A word an outlet puts in this many headlines about different names is its headline template
# ("Melhores momentos: ...", "Atuações do ...", "... - globoesporte.com"), not part of a story.
TEMPLATE_REPEATS = 4
# Words are compared by their first letters, so "retirar"/"retirada" and "câncer"/"cancerígeno" match.
STEM_LENGTH = 6

STOPWORDS = set("""
para pela pelo pelos pelas como mais menos sobre após apos entre contra desde até ate ainda após antes depois
quando onde qual quais quem porque porquê isso isto esse essa este esta esses essas estes estas aquele aquela
muito muita muitos muitas outro outra outros outras todo toda todos todas cada mesmo mesma seus suas nosso nossa
fazer feito pode podem deve devem será serão seria estão está estava foram sido sendo veja saiba confira entenda
diz dizem disse afirma segundo novo nova novos novas primeiro primeira segundo segunda hoje amanhã ontem
anos dias semana mês meses horas tempo vez vezes parte caso forma grande grandes maior menor melhor pior
brasil brasileiro brasileira brasileiros brasileiras país
with from that this they their there what when where which while about after before into over under than then
will would could should have has been being were says said new news first year years week today
""".split())


def _plain(text):
    text = unicodedata.normalize("NFKD", (text or "").casefold())
    return "".join(char for char in text if not unicodedata.combining(char))


_STOP = {_plain(word) for word in STOPWORDS}


_ROMAN = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}
_YEAR = re.compile(r"(?:19|20)\d\d")


def _roman(word):
    """'xiv' -> '14', so "Leão XIV" and "Leão 14" match; None for other words."""
    if not 2 <= len(word) <= 7 or set(word) - set(_ROMAN):
        return None
    total = 0
    for position, char in enumerate(word):
        value = _ROMAN[char]
        total += -value if position + 1 < len(word) and _ROMAN[word[position + 1]] > value else value
    return str(total) if total > 0 else None


def _lead(description):
    return re.split(r"(?<=[.!?])\s+", (description or "").strip(), maxsplit=1)[0]


def _words(title, description=""):
    """(stem, written as a name) for the words that say what a story is about.

    The description's first sentence adds the details outlets share about one fact. A word is
    written as a name when it is capitalized away from the start of a sentence.
    """
    for text in (title or "", _lead(description)):
        for position, match in enumerate(re.finditer(r"[^\W_]+", text)):
            raw = match.group()
            word = _roman(_plain(raw)) or _plain(raw)
            if word in _STOP or not (len(word) >= 4 or (any(char.isdigit() for char in word) and len(word) >= 2)):
                continue
            yield word[:STEM_LENGTH], position > 0 and raw[:1].isupper()


def stems(title, description=""):
    """The words that say what a story is about, cut to STEM_LENGTH letters."""
    return frozenset(stem for stem, _ in _words(title, description))


def _templates(ordered, words, names):
    """{source id: words that outlet repeats in stories about different names}.

    A story's headlines keep naming the same someone ("Papa", "Leão"); a template's headlines name
    someone new each time ("Melhores momentos: Hamburg x Stuttgart", "... Dortmund ..."). A name the
    template always carries ("pelo Alemão") is template too, so this repeats until nothing changes.
    """
    by_source = defaultdict(list)
    for content in ordered:
        by_source[content.get("source_id")].append(words[content["id"]])   # headline and lead sentence
    templates = {}
    for source, headlines in by_source.items():
        found = frozenset()
        for _ in range(4):
            uses = defaultdict(list)                       # word -> the other names of each headline using it
            for headline in headlines:
                for word in headline - found:
                    uses[word].append((headline & names) - found - {word})
            grown = found | {
                word for word, others in uses.items()
                if len(others) >= TEMPLATE_REPEATS
                and sum(1 for other in others if other) * 2 >= len(others)
                and max(Counter(name for other in others for name in other).values(), default=0) * 4 <= len(others) * 3}
            if grown == found:
                break
            found = grown
        templates[source] = found
    return templates


def _similarity(a, b, weight, names=frozenset(), uncommon=None, ignored=frozenset()):
    shared = (a & b) - ignored
    rare = shared if uncommon is None else shared & uncommon
    facts = {word for word in rare - names if not _YEAR.fullmatch(word)}
    if len(shared) < MIN_SHARED_WORDS or len(rare & names) < MIN_SHARED_NAMES or len(facts) < MIN_SHARED_FACT_WORDS:
        return 0.0
    return sum(weight[word] for word in shared) / max(1e-9, min(sum(weight[word] for word in a), sum(weight[word] for word in b)))


def explain_pair(contents, story_a, story_b):
    """Why two stories of ``contents`` are or are not one story (for diagnosing threads)."""
    return story_threads(contents, explain=(story_a, story_b))


def story_threads(contents, explain=None):
    """{article id: thread id} for indexed articles (dicts with id, title, description, source_id, published_at, event_id).

    Articles of one event always share a thread. A thread's id is the event (or article) id of its
    oldest story, so it stays the same while newer coverage joins it.
    """
    ordered = sorted(contents, key=lambda content: (content["published_at"] or "", content["id"]))
    repeated = Counter(_plain(_lead(content.get("description"))) for content in ordered)
    words, as_name, as_word = {}, Counter(), Counter()
    for content in ordered:
        description = content.get("description")
        if repeated[_plain(_lead(description))] >= BOILERPLATE_REPEATS:
            description = ""
        found = list(_words(content["title"], description))
        words[content["id"]] = frozenset(stem for stem, _ in found)
        for stem, capitalized in found:
            (as_name if capitalized else as_word)[stem] += 1
    # A name is a word the stories write capitalized more often than not ("Lula", "Botafogo").
    names = frozenset(stem for stem in as_name if as_name[stem] > as_word[stem])
    frequency = Counter(word for content in ordered for word in words[content["id"]])
    total = max(1, len(ordered))
    weight = {word: math.log(1 + total / count) for word, count in frequency.items()}
    # Only words rare enough to tell stories apart are used to find candidate threads.
    rare_limit = max(8, int(total * 0.02))
    uncommon = frozenset(word for word, count in frequency.items() if count <= rare_limit)
    templates = _templates(ordered, words, names)
    source_of = {content["id"]: content.get("source_id") for content in ordered}
    def ignored_for(story_id, other_id):
        return templates.get(source_of[story_id], frozenset()) | templates.get(source_of[other_id], frozenset())
    def similarity(story_id, other_id):
        return _similarity(words[story_id], words[other_id], weight, names, uncommon, ignored_for(story_id, other_id))
    if explain:
        a, b = explain
        shared = words[a] & words[b]
        return {"words_a": sorted(words[a]), "words_b": sorted(words[b]), "shared": sorted(shared),
                "shared_names": sorted(shared & names), "shared_uncommon": sorted(shared & uncommon),
                "ignored_as_template": sorted(shared & ignored_for(a, b)),
                "similarity": round(similarity(a, b), 3), "rare_limit": rare_limit}
    postings = defaultdict(list)          # word -> thread ids with a story using it
    members = defaultdict(list)           # thread id -> article ids
    thread_of, thread_of_event = {}, {}
    for content in ordered:
        story_id, event_id = content["id"], content.get("event_id")
        story_words = words[story_id]
        thread = thread_of_event.get(event_id) if event_id else None
        if thread is None:
            candidates = {candidate for word in story_words if frequency[word] <= rare_limit for candidate in postings[word]}
            best, best_score = None, THREAD_SIMILARITY
            for candidate in sorted(candidates):
                scores = [similarity(story_id, member) for member in members[candidate]]
                score = max(scores)
                support = sum(value >= THREAD_SIMILARITY for value in scores)
                if (score >= best_score and scores[0] >= ANCHOR_SIMILARITY
                        and support >= (MIN_SUPPORT if len(scores) >= SUPPORT_FROM else 1)):
                    best, best_score = candidate, score
            thread = best or event_id or story_id
        thread_of[story_id] = thread
        if event_id:
            thread_of_event.setdefault(event_id, thread)
        members[thread].append(story_id)
        for word in story_words:
            if frequency[word] <= rare_limit and (not postings[word] or postings[word][-1] != thread):
                postings[word].append(thread)
    return thread_of
