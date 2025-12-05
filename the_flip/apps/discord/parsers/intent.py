"""Intent classification for Discord messages."""

from __future__ import annotations

from .types import RecordType

# Keywords for classification (single words only - matched via word splitting)
PARTS_KEYWORDS = {"need", "order", "part", "parts", "buy", "purchase", "ordering"}
PROBLEM_KEYWORDS = {"broken", "stuck", "dead", "issue", "problem"}
WORK_KEYWORDS = {
    "fixed",
    "replaced",
    "cleaned",
    "adjusted",
    "repaired",
    "installed",
    "swapped",
    "changed",
}

# Phrases for classification (multi-word - matched via substring)
PROBLEM_PHRASES = ["not working", "doesnt work", "doesn't work", "won't start", "wont start"]
WORK_PHRASES = ["worked on"]


def _has_keywords(
    content_lower: str, words: set[str], keywords: set[str], phrases: list[str] | None = None
) -> bool:
    """Check if content contains any of the keywords or phrases."""
    # Check single-word keywords
    if words & keywords:
        return True
    # Check multi-word phrases
    if phrases:
        for phrase in phrases:
            if phrase in content_lower:
                return True
    return False


def has_work_keywords(content: str) -> bool:
    """Check if content contains work-related keywords or phrases."""
    content_lower = content.lower()
    words = set(content_lower.split())
    return _has_keywords(content_lower, words, WORK_KEYWORDS, WORK_PHRASES)


def classify_intent(content: str) -> RecordType:
    """Classify message intent based on keywords.

    Pure function with no database access. Returns the record type
    that should be created based on keyword matching.

    Priority order:
    1. Parts keywords -> PART_REQUEST
    2. Problem keywords/phrases -> PROBLEM_REPORT
    3. Work keywords/phrases or default -> LOG_ENTRY

    Args:
        content: The message text to classify

    Returns:
        The appropriate RecordType for the message content.
    """
    content_lower = content.lower()
    words = set(content_lower.split())

    if _has_keywords(content_lower, words, PARTS_KEYWORDS):
        return RecordType.PART_REQUEST

    if _has_keywords(content_lower, words, PROBLEM_KEYWORDS, PROBLEM_PHRASES):
        return RecordType.PROBLEM_REPORT

    # Work keywords or default - both result in LOG_ENTRY
    return RecordType.LOG_ENTRY
