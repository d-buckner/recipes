import re

# FTS5 special characters that need escaping
_FTS5_SPECIAL = re.compile(r'["\^\*\(\)\{\}\[\]\~\+\-\!\&\|\:\.]')


def sanitize_fts_query(query: str) -> str:
    """
    Escape FTS5 special characters and wrap each token in double quotes
    for safe substring matching with the trigram tokenizer.
    """
    query = query.strip()
    if not query:
        return '""'

    # Remove/escape special chars
    query = _FTS5_SPECIAL.sub(" ", query)

    tokens = query.split()
    if not tokens:
        return '""'

    # Wrap each token in double quotes for exact phrase matching
    escaped = " ".join(f'"{token}"' for token in tokens)
    return escaped
