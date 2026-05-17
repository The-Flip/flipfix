"""Pure display helpers for User/Maintainer rendering.

Kept template-tag-free so callers outside the template layer
(e.g. ``AppConfig.ready()`` link-type registration) can import without
pulling in permission filters or other template machinery.
"""

from __future__ import annotations

from typing import Any


def display_name_with_username(user: Any) -> str:
    """Return user's display name with username suffix.

    Returns ``"First Last (username)"`` when any name part is set,
    ``"First (username)"`` or ``"Last (username)"`` when only one is set,
    or the bare ``username`` when no name parts are set.

    Returns the empty string when ``user`` is falsy.
    """
    if not user:
        return ""
    first = getattr(user, "first_name", "") or ""
    last = getattr(user, "last_name", "") or ""
    username = getattr(user, "username", "") or ""
    if first or last:
        full_name = f"{first} {last}".strip()
        return f"{full_name} ({username})"
    return username
