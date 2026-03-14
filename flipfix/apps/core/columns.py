"""Utilities for building column-grid views grouped by a key."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from flipfix.apps.catalog.models import Location, MachineInstance
    from flipfix.apps.maintenance.models import ProblemReport

MAX_VISIBLE_REPORTS = 4


@dataclass
class MachineGroup:
    """A single machine and its open problem reports, grouped for column display."""

    machine: MachineInstance
    reports: list[ProblemReport]

    @property
    def sort_key(self) -> int:
        """Sort by the most severe (lowest priority_sort) report.

        ``priority_sort`` is an annotation added by queryset methods like
        :meth:`~flipfix.apps.maintenance.models.ProblemReportQuerySet.for_wall_display`
        and
        :meth:`~flipfix.apps.maintenance.models.ProblemReportQuerySet.for_open_by_location`.
        """
        return min(getattr(report, "priority_sort", 999) for report in self.reports)

    @property
    def visible_reports(self) -> list[ProblemReport]:
        """The first reports shown as full rows."""
        return self.reports[:MAX_VISIBLE_REPORTS]

    @property
    def overflow_summary(self) -> str:
        """Human-readable summary of reports beyond the visible limit.

        Returns e.g. "plus 3 minor and 2 task", or empty string if all
        reports are visible.
        """
        overflow = self.reports[MAX_VISIBLE_REPORTS:]
        if not overflow:
            return ""
        counts: Counter[str] = Counter()
        for report in overflow:
            counts[report.get_priority_display().lower()] += 1
        parts = [f"{count} {label}" for label, count in counts.items()]
        if len(parts) <= 2:
            return "plus " + " and ".join(parts)
        return "plus " + ", ".join(parts[:-1]) + ", and " + parts[-1]


def group_by_machine(reports: list[ProblemReport]) -> list[MachineGroup]:
    """Group reports by machine, preserving severity ordering within each group."""
    by_machine: dict[int, list[ProblemReport]] = defaultdict(list)
    machine_order: list[int] = []
    machines: dict[int, MachineInstance] = {}
    for report in reports:
        pk = report.machine_id
        if pk not in machines:
            machines[pk] = report.machine
            machine_order.append(pk)
        by_machine[pk].append(report)

    groups = [MachineGroup(machine=machines[pk], reports=by_machine[pk]) for pk in machine_order]
    groups.sort(key=lambda g: g.sort_key)
    return groups


@dataclass
class Column:
    """A single column in a column-grid layout."""

    label: str
    items: list
    overflow_count: int = 0


def build_location_columns(
    reports: Iterable,
    locations: Iterable[Location],
    *,
    include_empty_columns: bool = True,
    max_results_per_column: int | None = None,
) -> list[Column]:
    """Group reports by their machine's location into ordered columns.

    Returns a list of :class:`Column` objects in the order of *locations*.
    Reports for machines with no location are appended in an ``"Unassigned"``
    column at the end, if any exist.

    When *include_empty_columns* is ``False``, locations with no reports are
    omitted.

    When *max_results_per_column* is set, each column's items are truncated and
    :attr:`Column.overflow_count` indicates how many additional items were
    not included.

    The returned shape is intentionally generic so the column-grid template
    partial can render any kind of grouped data.
    """
    by_location: dict[int, list] = defaultdict(list)
    unassigned: list = []

    for report in reports:
        loc_id = report.machine.location_id
        if loc_id:
            by_location[loc_id].append(report)
        else:
            unassigned.append(report)

    columns: list[Column] = []
    for location in locations:
        items = by_location.get(location.pk, [])
        if not include_empty_columns and not items:
            continue
        columns.append(_make_column(location.name, items, max_results_per_column))

    if unassigned:
        columns.append(_make_column("Unassigned", unassigned, max_results_per_column))

    return columns


def _make_column(label: str, items: list, max_items: int | None) -> Column:
    """Build a :class:`Column`, truncating if *max_items* is set."""
    if max_items is None or len(items) <= max_items:
        return Column(label=label, items=items)
    return Column(label=label, items=items[:max_items], overflow_count=len(items) - max_items)
