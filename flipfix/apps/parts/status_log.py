"""The status-change line Flipfix writes into a part request update.

Changing a part request's status records a
:class:`~flipfix.apps.parts.models.PartRequestUpdate` whose text starts with an
automatic "Status changed: Ordered → Received" line, optionally followed by
whatever the person typed. Other code needs to tell the two apart — Discord
coalescing treats a bare status flip as bookkeeping but a flip with a note as
something worth reading.

Keeping the builder and the parser together means they can't drift apart.
"""

from __future__ import annotations

import re

_ARROW = "→"

_STATUS_CHANGE_LINE = re.compile(rf"^Status changed: .+? {_ARROW} [^\r\n]+\r?\n?")


def status_change_text(old_display: str, new_display: str) -> str:
    """The automatic first line of a status-change update."""
    return f"Status changed: {old_display} {_ARROW} {new_display}"


def status_change_comment(text: str) -> str:
    """Return what a person typed on a status-change update, or "" if nothing.

    Text that isn't a status change at all is returned unchanged — it is all
    comment.
    """
    return _STATUS_CHANGE_LINE.sub("", (text or "").strip(), count=1).strip()
