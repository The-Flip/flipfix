"""Machine name matching for Discord messages."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def find_machine_name(content: str, machine_names: list[str]) -> str | None:
    """Find a machine name in the message content.

    Pure string-matching function with no database access.

    Args:
        content: The message text to search
        machine_names: List of machine display names to match against

    Returns:
        The matched machine name if exactly one match, None otherwise.
    """
    content_lower = content.lower()
    matches: list[tuple[str, str]] = []  # (name, match_type)

    for name in machine_names:
        name_lower = name.lower()

        # Exact match on display name
        if name_lower in content_lower:
            matches.append((name, "exact"))
            continue

        # Prefix match: "godzilla" matches "Godzilla (Premium)"
        # Split display name into first word for prefix matching
        first_word = name_lower.split()[0] if name_lower else ""
        if first_word and len(first_word) >= 4:  # Avoid short matches
            # Check if first word appears as a whole word in content
            if re.search(rf"\b{re.escape(first_word)}\b", content_lower):
                matches.append((name, "prefix"))

    # Remove duplicates (same name matched multiple ways)
    unique_names: dict[str, str] = {}
    for name, match_type in matches:
        if name not in unique_names:
            unique_names[name] = match_type

    if len(unique_names) == 1:
        name, match_type = list(unique_names.items())[0]
        logger.info(
            "discord_machine_matched",
            extra={
                "machine_name": name,
                "match_type": match_type,
            },
        )
        return name
    elif len(unique_names) > 1:
        logger.info(
            "discord_machine_ambiguous",
            extra={
                "matches": list(unique_names.keys()),
                "content_preview": content[:100],
            },
        )
        return None
    else:
        return None
