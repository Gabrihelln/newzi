"""Article search over the content index."""


def search_clause(db, query):
    """SQL condition (on alias ``c``) and parameters matching ``query`` in title or description."""
    pattern = "%" + str(query)[:100].lower() + "%"
    return "(LOWER(c.title) LIKE ? OR LOWER(c.description) LIKE ?)", [pattern, pattern]
