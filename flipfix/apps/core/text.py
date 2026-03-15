"""Text utilities for the core app."""

import re

_LEADING_ARTICLE_RE = re.compile(r"^(The|A|An)\s+", re.IGNORECASE)


def strip_leading_articles(name: str) -> str:
    """Strip leading English articles ('The', 'A', 'An') for sorting purposes.

    Returns the original name if stripping would produce an empty string
    (e.g. the name is just "The").
    """
    result = _LEADING_ARTICLE_RE.sub("", name)
    return result if result else name
