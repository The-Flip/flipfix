"""Persist the known parity gaps so the list can only shrink.

The file has two sections and the distinction matters:

``gaps``
    The ratchet. Real defects we have not fixed yet. ``--update-baseline``
    maintains this section, and the regression test fails both when it grows
    (a new gap) and when an entry stops reproducing without being deleted (a
    fixed gap left behind).

``accepted``
    Differences that are deliberate, each carrying a written reason. Never
    written automatically: promoting an entry is a hand edit, which puts it in
    front of a reviewer. Without this section the intentional differences would
    sit in ``gaps`` forever and "the list only shrinks" would be a fiction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flipfix.apps.core.mobile_parity.audit import AuditResult, Gap
from flipfix.apps.core.mobile_parity.config import DESKTOP_WIDTH, MOBILE_WIDTH

SCHEMA_VERSION = 1
BASELINE_PATH = Path(__file__).parent / "baseline.json"

Identity = tuple[str, str, str]


class BaselineError(Exception):
    """The baseline file is missing required information."""


@dataclass(frozen=True)
class BaselineEntry:
    """One recorded gap.

    Only ``route``, ``persona`` and ``key`` take part in matching. The rest is
    description that ``--update-baseline`` refreshes freely, so innocuous markup
    churn shows up in the diff without failing the build.
    """

    route: str
    persona: str
    key: str
    kind: str = ""
    element: str = ""
    label: str = ""
    hidden_by: str = ""
    revealed_at: int | None = None
    note: str = ""
    reason: str = ""

    @property
    def identity(self) -> Identity:
        return (self.route, self.persona, self.key)

    @classmethod
    def from_gap(cls, gap: Gap, *, note: str = "") -> BaselineEntry:
        return cls(
            route=gap.route,
            persona=gap.persona,
            key=gap.key,
            kind=gap.kind,
            element=gap.element,
            label=gap.label,
            hidden_by=gap.hidden_by,
            revealed_at=gap.revealed_at,
            note=note,
        )

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "route": self.route,
            "persona": self.persona,
            "key": self.key,
            "kind": self.kind,
            "element": self.element,
            "label": self.label,
            "hidden_by": self.hidden_by,
            "revealed_at": self.revealed_at,
        }
        if self.note:
            payload["note"] = self.note
        if self.reason:
            payload["reason"] = self.reason
        return payload


@dataclass(frozen=True)
class Baseline:
    """The committed record of what we already know about."""

    gaps: tuple[BaselineEntry, ...] = ()
    accepted: tuple[BaselineEntry, ...] = ()
    mobile_width: int = MOBILE_WIDTH
    desktop_width: int = DESKTOP_WIDTH

    @property
    def identities(self) -> set[Identity]:
        return {entry.identity for entry in (*self.gaps, *self.accepted)}


@dataclass(frozen=True)
class BaselineDiff:
    """What changed between the baseline and a fresh audit."""

    new: tuple[Gap, ...]
    stale: tuple[BaselineEntry, ...]
    reproduced: tuple[BaselineEntry, ...]
    accepted_reproduced: tuple[BaselineEntry, ...]

    @property
    def is_clean(self) -> bool:
        return not self.new and not self.stale


def _entry_from_dict(payload: dict[str, Any], *, section: str) -> BaselineEntry:
    missing = {"route", "persona", "key"} - payload.keys()
    if missing:
        raise BaselineError(f"{section} entry {payload!r} is missing {sorted(missing)}.")
    entry = BaselineEntry(
        route=payload["route"],
        persona=payload["persona"],
        key=payload["key"],
        kind=payload.get("kind", ""),
        element=payload.get("element", ""),
        label=payload.get("label", ""),
        hidden_by=payload.get("hidden_by", ""),
        revealed_at=payload.get("revealed_at"),
        note=payload.get("note", ""),
        reason=payload.get("reason", ""),
    )
    if section == "accepted" and not entry.reason.strip():
        raise BaselineError(
            f"accepted entry {entry.identity} has no 'reason'. An accepted parity "
            "difference must say why it is deliberate, otherwise it is just an "
            "unrecorded bug."
        )
    return entry


def load_baseline(path: Path | None = None) -> Baseline:
    """Read the committed baseline, or an empty one if it does not exist yet."""
    path = path or BASELINE_PATH
    if not path.exists():
        return Baseline()
    payload = json.loads(path.read_text(encoding="utf-8"))
    widths = payload.get("widths", {})
    return Baseline(
        gaps=tuple(_entry_from_dict(item, section="gaps") for item in payload.get("gaps", [])),
        accepted=tuple(
            _entry_from_dict(item, section="accepted") for item in payload.get("accepted", [])
        ),
        mobile_width=widths.get("mobile", MOBILE_WIDTH),
        desktop_width=widths.get("desktop", DESKTOP_WIDTH),
    )


def _visited(result: AuditResult) -> set[tuple[str, str]]:
    """The ``(route, persona)`` pairs this run actually rendered."""
    return set(result.audited)


def diff_against(result: AuditResult, baseline: Baseline) -> BaselineDiff:
    """Compare a fresh audit with the baseline in both directions.

    Failing on stale entries as well as new ones is what forces the list to
    shrink: fixing a gap without deleting its record is itself an error.

    Staleness is only judged for pages this run actually rendered. A page that
    was filtered out with ``--route``, or that stopped returning HTML, tells us
    nothing about whether its gaps were fixed — calling those entries stale
    would invite deleting records of defects that are still there.
    """
    observed = {gap.identity: gap for gap in result.gaps}
    accepted = {entry.identity for entry in baseline.accepted}
    visited = _visited(result)

    new = tuple(
        gap for identity, gap in sorted(observed.items()) if identity not in baseline.identities
    )
    stale = tuple(
        entry
        for entry in (*baseline.gaps, *baseline.accepted)
        if (entry.route, entry.persona) in visited and entry.identity not in observed
    )
    reproduced = tuple(entry for entry in baseline.gaps if entry.identity in observed)
    accepted_reproduced = tuple(
        entry
        for entry in baseline.accepted
        if entry.identity in observed and entry.identity in accepted
    )
    return BaselineDiff(
        new=new,
        stale=stale,
        reproduced=reproduced,
        accepted_reproduced=accepted_reproduced,
    )


def build_updated(result: AuditResult, baseline: Baseline, *, accept_new: bool) -> Baseline:
    """Return the baseline as it should be written back.

    Stale entries are always dropped. New gaps are only recorded when
    ``accept_new`` is set, so silencing a regression takes a deliberate second
    flag and shows up as a *grown* list in review.
    """
    observed = {gap.identity: gap for gap in result.gaps}
    notes = {entry.identity: entry.note for entry in baseline.gaps}
    visited = _visited(result)

    def survives(entry: BaselineEntry) -> bool:
        # Keep entries for pages this run did not render: we have no evidence
        # about them, and dropping them would quietly erase known defects.
        return entry.identity in observed or (entry.route, entry.persona) not in visited

    kept = [
        BaselineEntry.from_gap(observed[entry.identity], note=notes.get(entry.identity, ""))
        if entry.identity in observed
        else entry
        for entry in baseline.gaps
        if survives(entry)
    ]
    if accept_new:
        known = baseline.identities
        kept.extend(
            BaselineEntry.from_gap(gap)
            for identity, gap in sorted(observed.items())
            if identity not in known
        )

    accepted = tuple(entry for entry in baseline.accepted if survives(entry))
    return Baseline(
        gaps=tuple(sorted(kept, key=lambda entry: entry.identity)),
        accepted=tuple(sorted(accepted, key=lambda entry: entry.identity)),
        mobile_width=result.mobile_width,
        desktop_width=result.desktop_width,
    )


def write_baseline(baseline: Baseline, path: Path | None = None) -> None:
    """Write the baseline deterministically so its diffs stay readable."""
    path = path or BASELINE_PATH
    payload = {
        "schema_version": SCHEMA_VERSION,
        "widths": {"mobile": baseline.mobile_width, "desktop": baseline.desktop_width},
        "gaps": [entry.as_dict() for entry in baseline.gaps],
        "accepted": [entry.as_dict() for entry in baseline.accepted],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
