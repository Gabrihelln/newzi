"""Conservative entity normalization and provenance-aware grounding for Phase 3.3."""
import re
import unicodedata


def normalize_entity(value):
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    value = value.replace("&", " e ")
    value = re.sub(r"[�?T'`\".,:;()\[\]]", " ", value)
    return " ".join(value.split())


SAFE_EQUIVALENCES = {
    "gm": "general motors", "general motors": "gm",
    "ai": "artificial intelligence", "artificial intelligence": "ai",
    "ia": "inteligencia artificial", "inteligencia artificial": "ia",
    "apple inc": "apple", "apple": "apple inc",
    "wired": "wired",
    "agentic": "ag entic", "ag entic": "agentic",
    "agência": "agency",
}

TRANSLATION_EQUIVALENCES = {
    "atlas de ia e economia": ("ai economy atlas", "atlas"),
    "agêntica": ("agentic",),
    "inteligência artificial": ("artificial intelligence", "ai"),
    "ficção personalizada": ("custom fiction",),
}


class EntityGroundingValidatorV2:
    def _texts(self, event):
        content, title, metadata = [], [], []
        for article in event.get("articles", []):
            content.append(article.get("description", article.get("content", "")))
            title.append(article.get("title", ""))
            metadata.extend([article.get("source", article.get("source_name", "")), article.get("publisher", ""), article.get("url", "")])
        return " ".join(content), " ".join(title), " ".join(metadata)

    def check(self, entity, event):
        target = normalize_entity(entity)
        content, title, metadata = [normalize_entity(x) for x in self._texts(event)]
        if not target:
            return False, "EMPTY", ""
        if target in content:
            return True, "CONTENT", target
        if target in title:
            return True, "TITLE", target
        if target in metadata:
            return True, "SOURCE_METADATA", target
        aliases = {target, SAFE_EQUIVALENCES.get(target, "")}
        aliases.update(TRANSLATION_EQUIVALENCES.get(target, ()))
        searchable = (content + " " + title + " " + metadata)
        for alias in aliases:
            alias = normalize_entity(alias)
            if alias and alias in searchable:
                provenance = "SOURCE_METADATA" if alias in metadata else ("TITLE" if alias in title else "CONTENT")
                return True, provenance, alias
        return False, "UNSUPPORTED", target

