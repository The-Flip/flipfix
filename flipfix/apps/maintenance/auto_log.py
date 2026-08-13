"""The log entries Flipfix writes on a person's behalf.

Several places create a :class:`~flipfix.apps.maintenance.models.LogEntry` that
nobody typed: :mod:`flipfix.apps.maintenance.signals` records machine creation,
status and location changes, and the problem-report views record a close or
re-open.  Those texts are user-visible strings, and other code needs to tell them
apart from what a person actually wrote — Discord coalescing, for instance,
promotes a hand-written entry to a full post but folds an automatic one into a
one-line summary.

Keeping the builders and the classifier in one module means the two can't drift:
a caller that changes the wording changes the pattern that recognises it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

# The arrow used in "old → new" texts.
_ARROW = "→"

CLOSED_REPORT_TEXT = "Closed problem report"
REOPENED_REPORT_TEXT = "Re-opened problem report"


class AutoLogKind(StrEnum):
    """Which automatic log entry a piece of text is."""

    MACHINE_ADDED = "machine_added"
    STATUS_CHANGED = "status_changed"
    LOCATION_CHANGED = "location_changed"
    MOVED_TO_FLOOR = "moved_to_floor"
    REPORT_CLOSED = "report_closed"
    REPORT_REOPENED = "report_reopened"


@dataclass(frozen=True)
class AutoLog:
    """A recognised automatic log entry, and the new value where there is one."""

    kind: AutoLogKind
    detail: str = ""

    @property
    def action_label(self) -> str:
        """A short phrase naming the action, for grouping several of them together.

        Reads as a heading over a list of machines, e.g. "Marked Good" over
        "Tempest, Centipede".
        """
        match self.kind:
            case AutoLogKind.MACHINE_ADDED:
                return "Added"
            case AutoLogKind.STATUS_CHANGED:
                return f"Marked {self.detail}" if self.detail else "Status changed"
            case AutoLogKind.LOCATION_CHANGED:
                return f"Moved to {self.detail}" if self.detail else "Moved"
            case AutoLogKind.MOVED_TO_FLOOR:
                return "Moved to the floor"
            case AutoLogKind.REPORT_CLOSED:
                return "Closed a problem report"
            case AutoLogKind.REPORT_REOPENED:
                return "Re-opened a problem report"


# --- Builders -------------------------------------------------------------
# The only supported way to write these texts. Update the matching pattern below
# whenever one of these changes.


def machine_added_text(machine_name: str) -> str:
    return f"New machine added: {machine_name}"


def status_changed_text(old_display: str, new_display: str) -> str:
    return f"Status changed: {old_display} {_ARROW} {new_display}"


def location_changed_text(old_name: str, new_name: str) -> str:
    return f"Location changed: {old_name} {_ARROW} {new_name}"


def moved_to_floor_text(machine_name: str) -> str:
    return f"\U0001f389\U0001f38a {machine_name} has moved to the floor!"


# --- Classifier -----------------------------------------------------------

_PATTERNS: tuple[tuple[AutoLogKind, re.Pattern[str]], ...] = (
    (AutoLogKind.MACHINE_ADDED, re.compile(r"^New machine added: (?P<detail>.+)$")),
    (AutoLogKind.STATUS_CHANGED, re.compile(rf"^Status changed: .+ {_ARROW} (?P<detail>.+)$")),
    (AutoLogKind.LOCATION_CHANGED, re.compile(rf"^Location changed: .+ {_ARROW} (?P<detail>.+)$")),
    (AutoLogKind.MOVED_TO_FLOOR, re.compile(r"^\U0001f389\U0001f38a .+ has moved to the floor!$")),
    (AutoLogKind.REPORT_CLOSED, re.compile(rf"^{re.escape(CLOSED_REPORT_TEXT)}$")),
    (AutoLogKind.REPORT_REOPENED, re.compile(rf"^{re.escape(REOPENED_REPORT_TEXT)}$")),
)


def classify(text: str) -> AutoLog | None:
    """Recognise an automatic log entry, or return ``None`` for a hand-written one."""
    stripped = (text or "").strip()
    for kind, pattern in _PATTERNS:
        match = pattern.match(stripped)
        if match:
            detail = match.groupdict().get("detail", "") or ""
            return AutoLog(kind=kind, detail=detail.strip())
    return None
