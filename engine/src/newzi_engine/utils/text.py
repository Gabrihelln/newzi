import hashlib
import html
import re
import unicodedata
from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid", "mc_cid", "mc_eid"}
STOPWORDS = set("a an and are as at be by for from has in is it its of on or that the their this to was were with new news says about after before into over under via how why what when where will".split())

def clean_text(value: str | None) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()

# Texto lixo: what an outlet puts inside a story's text that is not the story (photo credits, paywall
# notices, "saiba mais"/"leia também" pointers, newsletter and WhatsApp plugs, feed footers, template tokens).
# Each rule matches the outlet's fixed wording or its position, so the same words used inside a sentence
# ("exclusivo para assinantes do Spotify Premium", "talvez saiba mais do que aparenta") stay.
_UPPER = "A-ZÁÉÍÓÚÂÊÔÃÕÇ"
_STOP = r"(?:O|A|Os|As|E|Em|No|Na|Nos|Nas|Um|Uma|Ao|À|De|Do|Da|Para|Por|Com|Se|Segundo|Mas|Ele|Ela|Eles|Elas|LEIA|VEJA|SAIBA|The|In|On|At|It|He|She|They|This)\b"
_WORD = rf"(?!{_STOP})(?:[{_UPPER}]\.|[{_UPPER}@][\w'’@&-]*(?:\.[\w'’@&-]+)*)"  # "Alexi J. Rosenfeld", "Planet.com", never "Fujimori."
_PART = rf"(?:{_WORD}(?:\s+(?:d[aeo]s?\s+)?{_WORD}){{0,3}}|[\w.@-]+(?=\s*/))"  # "Fernando Frazão", "Embaixada dos EUA"
# The credit's last name is two words only when a new sentence (or another credit) follows: "Agência Brasil O padre"
# loses "Agência Brasil", "@LulaOficial/ X Lula informou" keeps "Lula".
_LAST = rf"{_WORD}(?:\s+d[aeo]s?\s+{_WORD})*(?:\s+{_WORD}(?=\s*/|\s+[{_UPPER}“\"'‘]|\s*$))?"
_SEP = r"(?:\s*/\s*(?:via\s+)?|\s+via\s+)"
# A credit is found by its agency word, then widened over the names joined to it by "/" or "via":
# "Anadolu via Getty Images (BBC)", "Hasnoor Hussain/Reuters", "Reprodução/Arquivo", "Foto: Petrobras/Divulgação".
_CREDIT_KEY = re.compile(r"\b(?P<colon>Fotos?|Imagem|Reprodução)\s*:"
                         r"|\b(?P<strong>Getty Images|Shutterstock)\b"
                         r"|\b(?P<weak>Getty|Divulgação|Reprodução|Reuters|REUTERS|AFP|EPA|Agência Brasil)\b")
_CREDIT_LEFT = re.compile(rf"(?:{_PART}{_SEP})+$")
_CREDIT_RIGHT = re.compile(rf"(?:{_SEP}{_LAST})*(?:\s*\(BBC\))?")
_CREDIT_COLON = re.compile(rf"\s*(?:Arquivo pessoal|(?:{_PART}{_SEP})*{_LAST})")
_CREDIT_DASH = re.compile(r"\s[-–—]\s+$")  # "... em Nova York - Foto: @LulaOficial/ X"
_RIGHT_ONLY = {"Getty", "Divulgação", "Reprodução", "REUTERS"}  # agency words that may open a credit: "REUTERS/Remo Casilli"
_SENTENCE_END = (".", "!", "?", "…", "\"", "”")
_EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50\u2B55\uFE0F\u200D]+")  # the pictographs that open plugs: check mark, newspaper, headphones
_JUNK_TEMPLATE = re.compile(r"\{\{\s*[A-Z_]+\s*\}\}")  # {{WHATSAPP_CHANNEL}}
_JUNK_PAYWALL = re.compile(r"(^|[.!?|]\s*)(?i:(?:(?:matéria|conteúdo|reportagem|texto|artigo)\s+)?exclusiv[oa]\s+para\s+assinantes)\s*(?=[.!|:]|$)[.!|:]?"
                           r"|(?i:para ter acesso completo, acesse o link da matéria[^.]*\.?)")


def _opener(*phrases):
    """A phrase that opens a sentence or a clause: capitalized anywhere, lowercase only after punctuation."""
    caps = "|".join(f"{p[0].upper()}(?i:{p[1:]})" for p in phrases)
    lows = "|".join(phrases)
    return rf"(?:\b(?:{caps})|(?:^|(?<=[.!?;:(|>–—-])|(?<=[.!?;:(|>–—-]\s))(?:{lows}))"


_JUNK_POINTER = re.compile(r"\(\s*(?i:saiba|leia|veja)(?i:\s+mais)[^()]{0,40}\)")  # (saiba mais abaixo)
# "Saiba mais no Repórter Brasil Tarde", "saiba mais clicando aqui", "Saiba mais a seguir:": the pointer goes, the story stays.
_JUNK_SAIBA = re.compile(r"(?:[Ss]aiba|SAIBA)\s+(?:mais|Mais|MAIS)(?=\s*(?:abaixo|a seguir|aqui|clicando|n[oa]s?\b|em\b|sobre\b|[.:;!]|$|\{\{))[^.!?:]*[.!?:]?")


def _drop_saiba(match):
    before = match.string[:match.start()].rstrip()
    if match.group().startswith("saiba") and before and before[-1] not in ".!?;:(|>–—-":
        return match.group()  # lowercase inside a sentence: the verb, not a pointer
    return "." if before[-1:] in ";-–—" else " "


# Plugs removed on their own, each with a word it needs (lowercase) so most texts skip it.
_JUNK_SENTENCES = tuple((hint, re.compile(pattern)) for hint, pattern in (
    ("mais notícias", r"\+?\s*\b(?:Leia|Veja) mais notícias (?:d[aeo]s?|sobre)\s+(?:[^.+\s]+\s+){0,6}?[^.+\s]+(?=\s*[.+✅🗞🎧📲]|\s*$)\.?"),  # Leia mais notícias do Figueirense ✅
    ("mais notícias", r"\+?\s*\b(?:Leia|Veja) mais notícias (?:d[aeo]s?|sobre)\s+(?:[a-zà-ú][\w-]*\s+){0,4}[a-zà-ú][\w-]*(?=\s+[" + _UPPER + r"])"),  # +Veja mais notícias do esporte sul-mato-grossense
    ("whatsapp", r"[✅📱✨⌚️🗒️]*\s*\b(?:Clique aqui para seguir|Siga|Acesse|Acompanhe|Entre n)[oa]?s?\s+(?:o|a|os|as)?\s*[^.!?]{0,80}?\bno WhatsApp"
                 r"(?:\s+d[oa]\s+(?:CT|Canaltech|g1|ge)(?:\s+Ofertas)?)?(?:\s+para saber das (?:melhores )?promoções(?: de [a-zà-ú-]+)?)?\.?"),  # ✅ Siga o canal do g1 no WhatsApp
    ("sugestão de reportagem", r"[🗒️]*\s*Tem alguma sugestão de reportagem\? Mande para o g1\.?"),
    ("agora no g1", r"^\s*Agora no g1\b"),
    ("inscreva-se", r"Quer recebê-la [^?]{0,40}no seu e-?mail\? Inscreva-se abaixo:?"),
    ("inbox", r"Don[’']t get [^?]{1,80} delivered to your inbox\? Sign up here\.?"),
    ("inbox", r"This story (?:originally )?appeared in [^.]{1,80}newsletter[^.]*\. To get stories like this in your inbox first, sign up here\.?"),
    ("get our", r"\bGet our [^.]{0,80}(?:newsletter|email|app|podcast)\b"),                                    # Get our breaking news email, free app or daily news podcast
    ("sign up", r"\bSign up (?:to|for) [^.]{0,80}?(?:newsletter|weekly email)(?: featuring our best reads)?(?: here)?\.?"),
    ("clicando aqui", r"(?:^|(?<=[.!?]))\s*[^.!?]{0,80}?\bclicando aqui\b[^.!?]*[.!?]?"),                     # Acompanhe ... clicando aqui.
    ("clique aqui", _opener("clique aqui") + r"[^.!?]*[.!?]?"),                                                # Clique aqui para retornar ao menu.
    ("mais aqui", r"\bLeia mais aqui\b"),
    ("mais abaixo", r"\b(?:Leia|Veja) mais abaixo\b[.:]?"),
    ("fontes favoritas", r"[🔍]*\s*\bAdicione o (?:ge|g1) nas suas fontes favoritas do Google\b\.?"),
    ("ouça o podcast", r"[🎧]*\s*\bOuça o podcast (?:ge|g1)\b(?:\s+[" + _UPPER + r"][\w]*)*"),
    ("assista:", r"\+\s*Assista: tudo sobre [^.]{0,60}?no sportv"),
))
# Pointers to other stories, feed footers and closing plugs: everything from them on is not the story.
_JUNK_TAIL = re.compile(
    r"(?:" + _opener("leia mais", "leia também", "veja também", "continue lendo", "continue reading", "read more", "notícias relacionadas:")
    + r"|\[Read more\]|\bVeja mais (?:de [\w-]+ )?no Canaltech|\bSe você gostou do conteúdo, talvez"
    r"|\bAo vivo e on demand Acompanhe a programação da TV Brasil|\b(?:The|O) post\b.*?\b(?:appeared first on|apareceu primeiro em)).*$", re.S)


def _photo_credits(text: str):
    """(start, end) of each photo credit in the text."""
    position = 0
    while key := _CREDIT_KEY.search(text, position):
        window = max(position, key.start() - 150)
        left = _CREDIT_LEFT.search(text[window:key.start()])
        start = window + left.start() if left else key.start()
        if key.group("colon"):
            named = _CREDIT_COLON.match(text, key.end())
            if not named:
                position = key.end()  # "Imagem: o que muda": no name after it, so not a credit
                continue
            end = named.end()
            dash = _CREDIT_DASH.search(text[window:start])
            start = window + dash.start() if dash else start
        else:
            right = _CREDIT_RIGHT.match(text, key.end())
            end = right.end()
            if key.group("weak") and not left and not (key.group("weak") in _RIGHT_ONLY and end > key.end()):
                position = key.end()  # "Talitha Getty", "a Reuters informou": an agency named in the story
                continue
        yield start, end
        position = end


def _drop_photo_credits(text: str) -> str:
    kept, last = [], 0
    for start, end in _photo_credits(text):
        before = text[last:start]
        # The caption a credit closes has no full stop of its own: it starts after the last one.
        caption_start = max(before.rfind(mark) for mark in _SENTENCE_END) + 1
        caption = before[caption_start:]
        if last == 0 and len(before.split()) <= 30:
            before = ""  # a text that opens with a photo caption: the whole caption goes, full stops and all
        elif caption.strip() and len(caption.split()) <= 25:
            before = before[:caption_start]  # the photo caption glued to the credit goes with it
        kept.append(before + " "); last = end
    return "".join(kept) + text[last:]


# Words each rule needs (lowercase): most texts have none, and the rules are then not run at all.
_CREDIT_HINTS = ("getty", "shutterstock", "divulgação", "reprodução", "reuters", "afp", "epa", "agência brasil", "foto", "imagem")
_TAIL_HINTS = ("leia mais", "leia também", "veja também", "continue lendo", "continue reading", "read more", "notícias relacionadas",
               "veja mais", "gostou do conteúdo", "ao vivo e on demand", " post ")


_DANGLING_DASH = re.compile(r"[;\-–—]+\s*(?=[.!?])")  # "80 voos - ." once the pointer after the dash is gone
_SPACE_BEFORE_MARK = re.compile(r"\s+([,.;:!?])")
_DOUBLE_MARK = re.compile(r"([.!?])[.;:]+(?=\s|$)")
_LEADING_MARKS = re.compile(r"^[\s.;:,\-–—|]+")
_SPACES = re.compile(r"\s+")


class _Text:
    """The text being cleaned, with its lowercase form kept for the rules' word checks."""
    def __init__(self, value):
        self.value, self.lowered = value, value.lower()

    def has(self, *hints):
        return any(hint in self.lowered for hint in hints)

    def apply(self, pattern, replacement):
        cleaned = pattern.sub(replacement, self.value) if not callable(pattern) else pattern(self.value)
        if cleaned != self.value:
            self.value, self.lowered = cleaned, cleaned.lower()


@lru_cache(maxsize=2048)  # the same descriptions are served again and again
def strip_junk_text(value: str | None) -> str:
    """The story's text without texto lixo."""
    text = _Text(_JUNK_TEMPLATE.sub(" ", value or ""))
    if text.has("assinantes", "acesso completo"):
        text.apply(_JUNK_PAYWALL, lambda m: m.group(1) or " ")
    if text.has(*_CREDIT_HINTS):
        text.apply(_drop_photo_credits, None)
    if text.has("mais"):
        text.apply(_JUNK_POINTER, " ")
        text.apply(_JUNK_SAIBA, _drop_saiba)
    for hint, pattern in _JUNK_SENTENCES:
        if text.has(hint):
            text.apply(pattern, " ")
    if text.has(*_TAIL_HINTS):
        text.apply(_JUNK_TAIL, "")
    cleaned = _EMOJI.sub(" ", text.value)
    cleaned = _DANGLING_DASH.sub("", cleaned)
    cleaned = _SPACE_BEFORE_MARK.sub(r"\1", cleaned)
    cleaned = _DOUBLE_MARK.sub(r"\1", cleaned)
    cleaned = _LEADING_MARKS.sub("", cleaned)
    return _SPACES.sub(" ", cleaned).strip()

def normalize_title(value: str) -> str:
    value = clean_text(value)
    value = value.replace("Ã¢â‚¬â€", " ").replace("Ã¢â‚¬â€œ", " ").replace("Ã¢â‚¬â„¢", " ").replace("Ã¢â‚¬Å“", " ").replace("Ã¢â‚¬Â", " ")
    value = re.sub(r"[\u2010-\u2015\u2018\u2019\u201c\u201d]", " ", value).casefold()
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9\s]", " ", value).strip().replace("  ", " ")

def canonicalize_url(url: str) -> str:
    parts = urlsplit((url or "").strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in TRACKING]
    path = re.sub(r"/+$", "", parts.path) or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))

def article_id(source_id: str, canonical_url: str, title: str) -> str:
    key = canonical_url or f"{source_id}:{normalize_title(title)}"
    return hashlib.sha256(key.encode()).hexdigest()[:24]

def tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", normalize_title(text).replace(" ", " ")) if t not in STOPWORDS}

