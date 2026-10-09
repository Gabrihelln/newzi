"""Accent-insensitive full-text search over article titles and descriptions.

SQLite uses an FTS5 index (``content_search``) kept in sync by triggers; PostgreSQL uses a
GIN index over the accent-folded text. Both are created by migration 0003. Every query word
must match, as a prefix ("infla" finds "inflação").
"""
import re

from .db import POSTGRES

# Folding applied identically to the PostgreSQL index expression and to query words.
ACCENTED = "áàâãäåéèêëíìîïóòôõöúùûüçñýÿÁÀÂÃÄÅÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑÝ"
PLAIN = "aaaaaaeeeeiiiiooooouuuucnyyaaaaaaeeeeiiiiooooouuuucny"
_FOLD = str.maketrans(ACCENTED, PLAIN)
PG_SEARCH_DOCUMENT = f"to_tsvector('simple', translate(lower(COALESCE(title,'')||' '||COALESCE(description,'')), '{ACCENTED}', '{PLAIN}'))"
MAX_TERMS = 8


def query_terms(query):
    """Words of ``query``: lower-cased, accent-folded, alphanumeric only (safe to embed in a match expression)."""
    return re.findall(r"\w+", str(query)[:100].lower().translate(_FOLD))[:MAX_TERMS]


def search_clause(db, query):
    """SQL condition (on alias ``c``) and parameters restricting articles to those matching ``query``."""
    terms = query_terms(query)
    if not terms:
        return "1=0", []
    if db.dialect == POSTGRES:
        document = PG_SEARCH_DOCUMENT.replace("COALESCE(title", "COALESCE(c.title").replace("COALESCE(description", "COALESCE(c.description")
        return f"{document} @@ to_tsquery('simple', ?)", [" & ".join(term + ":*" for term in terms)]
    return "c.rowid IN (SELECT rowid FROM content_search WHERE content_search MATCH ?)", [" ".join(f'"{term}"*' for term in terms)]
