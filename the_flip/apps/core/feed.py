"""Unified activity feed: paginated entries across multiple models.

Provides a single entry point for fetching activity feeds, supporting both
machine-scoped and global (all machines) views. Machine-scoped feeds filter
by machine and exclude machine name from search. Global feeds include machine
info in select_related for display.

Each record type is registered as a FeedEntrySource, so adding a new type
means adding one source definition rather than editing two parallel modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db.models import Prefetch, QuerySet

from the_flip.apps.maintenance.models import LogEntry, ProblemReport
from the_flip.apps.parts.models import PartRequest, PartRequestUpdate

if TYPE_CHECKING:
    from collections.abc import Callable

    from the_flip.apps.catalog.models import MachineInstance

# Type alias for feed entries (all have occurred_at attribute)
FeedEntry = LogEntry | ProblemReport | PartRequest | PartRequestUpdate


class EntryType(StrEnum):
    """Entry types for feed items. StrEnum allows direct template comparison."""

    LOG = "log"
    PROBLEM_REPORT = "problem_report"
    PART_REQUEST = "part_request"
    PART_REQUEST_UPDATE = "part_request_update"


ALL_ENTRY_TYPES: tuple[str, ...] = tuple(EntryType)


@dataclass(frozen=True)
class FeedConfig:
    """Configuration for a machine feed filter tab."""

    title_suffix: str  # Appended to browser title, e.g. "· Logs"
    breadcrumb_label: str | None  # Final breadcrumb text, None for activity feed
    entry_types: tuple[str, ...]  # Which entry types to include (immutable)
    empty_message: str  # Shown when feed has no entries
    search_empty_message: str  # Shown when search has no results


FEED_CONFIGS: dict[str, FeedConfig] = {
    "all": FeedConfig(
        title_suffix="",
        breadcrumb_label=None,
        entry_types=ALL_ENTRY_TYPES,
        empty_message="No activity yet.",
        search_empty_message="No activity matches your search.",
    ),
    "logs": FeedConfig(
        title_suffix=" · Logs",
        breadcrumb_label="Logs",
        entry_types=(EntryType.LOG,),
        empty_message="No log entries yet.",
        search_empty_message="No log entries match your search.",
    ),
    "problems": FeedConfig(
        title_suffix=" · Problem Reports",
        breadcrumb_label="Problems",
        entry_types=(EntryType.PROBLEM_REPORT,),
        empty_message="No problem reports yet.",
        search_empty_message="No problem reports match your search.",
    ),
    "parts": FeedConfig(
        title_suffix=" · Part Requests",
        breadcrumb_label="Parts",
        entry_types=(EntryType.PART_REQUEST,),
        empty_message="No parts requests yet.",
        search_empty_message="No parts requests match your search.",
    ),
}


class PageCursor:
    """Pagination cursor for templates that expect page_obj interface.

    Used when merging multiple querysets where Django's Paginator can't be used.
    """

    def __init__(self, has_next: bool, page_num: int = 1):
        self._has_next = has_next
        self._page_num = page_num

    def has_next(self) -> bool:
        return self._has_next

    def next_page_number(self) -> int:
        return self._page_num + 1


@dataclass(frozen=True)
class FeedEntrySource:
    """Describes how to fetch one type of entry for the unified feed.

    Each source specifies:
    - entry_type: tag set on entries for template dispatch
    - get_base_queryset: returns queryset with model-specific select_related/prefetch_related
    - machine_filter_field: field name for .filter(**{field: machine})
    - global_select_related: additional select_related fields for global (non-machine) scope
    """

    entry_type: str
    get_base_queryset: Callable[[], QuerySet[Any]]
    machine_filter_field: str
    global_select_related: tuple[str, ...]


# --- Queryset factories for each entry type ---
#
# These return base querysets with model-specific select_related/prefetch_related.
# The caller adds machine filtering or global select_related as appropriate.


def _log_entry_queryset() -> QuerySet[LogEntry]:
    return LogEntry.objects.select_related("problem_report").prefetch_related(
        "maintainers__user", "media"
    )


def _problem_report_queryset() -> QuerySet[ProblemReport]:
    latest_log_prefetch = Prefetch(
        "log_entries",
        queryset=LogEntry.objects.order_by("-occurred_at"),
        to_attr="prefetched_log_entries",
    )
    return ProblemReport.objects.select_related("reported_by_user").prefetch_related(
        latest_log_prefetch, "media"
    )


def _part_request_queryset() -> QuerySet[PartRequest]:
    latest_update_prefetch = Prefetch(
        "updates",
        queryset=PartRequestUpdate.objects.order_by("-occurred_at"),
        to_attr="prefetched_updates",
    )
    return PartRequest.objects.select_related("requested_by__user").prefetch_related(
        "media", latest_update_prefetch
    )


def _part_request_update_queryset() -> QuerySet[PartRequestUpdate]:
    return PartRequestUpdate.objects.select_related(
        "posted_by__user", "part_request"
    ).prefetch_related("media")


# --- Source registry ---
#
# To add a new entry type to the feed:
# 1. Add an EntryType member
# 2. Write a queryset factory function above
# 3. Register a FeedEntrySource here
# 4. Create the entry template(s)
# 5. Update the dispatcher templates (activity_entry.html, global_activity_entry.html)

FEED_SOURCES: dict[str, FeedEntrySource] = {
    EntryType.LOG: FeedEntrySource(
        entry_type=EntryType.LOG,
        get_base_queryset=_log_entry_queryset,
        machine_filter_field="machine",
        global_select_related=("machine", "machine__model"),
    ),
    EntryType.PROBLEM_REPORT: FeedEntrySource(
        entry_type=EntryType.PROBLEM_REPORT,
        get_base_queryset=_problem_report_queryset,
        machine_filter_field="machine",
        global_select_related=("machine", "machine__model"),
    ),
    EntryType.PART_REQUEST: FeedEntrySource(
        entry_type=EntryType.PART_REQUEST,
        get_base_queryset=_part_request_queryset,
        machine_filter_field="machine",
        global_select_related=("machine", "machine__model"),
    ),
    EntryType.PART_REQUEST_UPDATE: FeedEntrySource(
        entry_type=EntryType.PART_REQUEST_UPDATE,
        get_base_queryset=_part_request_update_queryset,
        machine_filter_field="part_request__machine",
        global_select_related=("part_request__machine",),
    ),
}


def get_feed_page(
    page_num: int = 1,
    page_size: int = settings.LIST_PAGE_SIZE,
    search_query: str | None = None,
    machine: MachineInstance | None = None,
    entry_types: tuple[str, ...] = ALL_ENTRY_TYPES,
) -> tuple[list[FeedEntry], bool]:
    """Get a paginated page of activity entries.

    When machine is provided, returns entries scoped to that machine using
    machine-specific search (excludes machine name from search fields).
    When machine is None, returns entries across all machines with global
    search (includes machine name matching).

    Uses merge-sort style pagination: fetches just enough from each table
    to construct the requested page.

    Returns (page_items, has_next) tuple.
    """
    offset = (page_num - 1) * page_size
    # Fetch one extra to detect if more pages exist (countless pagination pattern)
    fetch_limit = offset + page_size + 1

    all_entries: list[FeedEntry] = []

    for entry_type in entry_types:
        source = FEED_SOURCES.get(entry_type)
        if source:
            all_entries.extend(_fetch_entries(source, machine, search_query, fetch_limit))

    # Sort by occurred_at descending (all entry types share this field)
    combined = sorted(
        all_entries,
        key=lambda x: x.occurred_at,
        reverse=True,
    )

    # Slice to requested page
    page_items = combined[offset : offset + page_size]
    has_next = len(combined) > offset + page_size

    return page_items, has_next


def _fetch_entries(
    source: FeedEntrySource,
    machine: MachineInstance | None,
    search_query: str | None,
    limit: int,
) -> list[Any]:
    """Fetch entries for a single source, scoped to machine or global."""
    queryset = source.get_base_queryset()

    if machine:
        queryset = queryset.filter(**{source.machine_filter_field: machine})
        if search_query:
            queryset = queryset.search_for_machine(search_query)  # type: ignore[attr-defined]
    else:
        queryset = queryset.select_related(*source.global_select_related)
        if search_query:
            queryset = queryset.search(search_query)  # type: ignore[attr-defined]

    queryset = queryset.order_by("-occurred_at")
    entries = list(queryset[:limit])

    # Tag entries for template dispatch (all models get entry_type attribute)
    for entry in entries:
        entry.entry_type = source.entry_type  # type: ignore[attr-defined]

    return entries
