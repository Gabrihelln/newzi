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
# A story joining a thread must also resemble the thread's first story, so threads cannot chain
# ("Papa recebe alta" -> "alta do dólar" -> ...).
ANCHOR_SIMILARITY = 0.25
# Two stories sharing fewer words are never one story, however rare the words.
MIN_SHARED_WORDS = 3
# Shared names (Lula, Flávio) say who a story is about, not what happened; two stories must also
# share this many words about the fact itself (alta, cirurgia, câncer).
MIN_SHARED_FACT_WORDS = 2
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


def _roman(word):
    """'xiv' -> '14', so "Leão XIV" and "Leão 14" match; None for other words."""
    if not 2 <= len(word) <= 7 or set(word) - set(_ROMAN):
        return None
    total = 0
    for position, char in enumerate(word):
        value = _ROMAN[char]
        total += -value if position + 1 < len(word) and _ROMAN[word[position + 1]] > value else value
    return str(total) if total > 0 else None


def _words(title, description=""):
    """(stem, written as a name) for the words that say what a story is about.

    The description's first sentence adds the details outlets share about one fact. A word is
    written as a name when it is capitalized away from the start of a sentence.
    """
    lead = re.split(r"(?<=[.!?])\s+", (description or "").strip(), maxsplit=1)[0]
    for text in (title or "", lead):
        for position, match in enumerate(re.finditer(r"[^\W_]+", text)):
            raw = match.group()
            word = _roman(_plain(raw)) or _plain(raw)
            if word in _STOP or not (len(word) >= 4 or (any(char.isdigit() for char in word) and len(word) >= 2)):
                continue
            yield word[:STEM_LENGTH], position > 0 and raw[:1].isupper()


def stems(title, description=""):
    """The words that say what a story is about, cut to STEM_LENGTH letters."""
    return frozenset(stem for stem, _ in _words(title, description))


def _similarity(a, b, weight, names=frozenset()):
    shared = a & b
    if len(shared) < MIN_SHARED_WORDS or len(shared - names) < MIN_SHARED_FACT_WORDS:
        return 0.0
    return sum(weight[word] for word in shared) / max(1e-9, min(sum(weight[word] for word in a), sum(weight[word] for word in b)))


def story_threads(contents):
    """{article id: thread id} for indexed articles (dicts with id, title, description, published_at, event_id).

    Articles of one event always share a thread. A thread's id is the event (or article) id of its
    oldest story, so it stays the same while newer coverage joins it.
    """
    ordered = sorted(contents, key=lambda content: (content["published_at"] or "", content["id"]))
    words, as_name, as_word = {}, Counter(), Counter()
    for content in ordered:
        found = list(_words(content["title"], content.get("description")))
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
                score = max(_similarity(story_words, words[member], weight, names) for member in members[candidate])
                anchor = _similarity(story_words, words[members[candidate][0]], weight, names)
                if score >= best_score and anchor >= ANCHOR_SIMILARITY:
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
