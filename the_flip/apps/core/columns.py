"""Utilities for building column-grid views grouped by a key."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from the_flip.apps.catalog.models import Location


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
