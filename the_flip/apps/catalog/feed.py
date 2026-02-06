"""Unified machine feed: paginated activity entries across multiple models.

This module provides a single entry point for fetching machine activity feeds,
supporting filtering by entry type (logs, problems, parts) and search queries.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.db.models import Prefetch

from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.maintenance.models import LogEntry, ProblemReport
from the_flip.apps.parts.models import PartRequest, PartRequestUpdate

# Type alias for feed entries (all have occurred_at attribute)
FeedEntry = LogEntry | ProblemReport | PartRequest | PartRequestUpdate

# Entry type constants for consistency
ENTRY_TYPE_LOG = "log"
ENTRY_TYPE_PROBLEM_REPORT = "problem_report"
ENTRY_TYPE_PART_REQUEST = "part_request"
ENTRY_TYPE_PART_REQUEST_UPDATE = "part_request_update"


@dataclass(frozen=True)
class FeedConfig:
    """Configuration for a machine feed filter."""

    title_suffix: str  # Appended to browser title, e.g. "· Logs"
    breadcrumb_label: str | None  # Final breadcrumb text, None for activity feed
    entry_types: tuple[str, ...]  # Which entry types to include (immutable)
    empty_message: str  # Shown when feed has no entries
    search_empty_message: str  # Shown when search has no results


FEED_CONFIGS: dict[str, FeedConfig] = {
    "all": FeedConfig(
        title_suffix="",
        breadcrumb_label=None,
        entry_types=(
            ENTRY_TYPE_LOG,
            ENTRY_TYPE_PROBLEM_REPORT,
            ENTRY_TYPE_PART_REQUEST,
            ENTRY_TYPE_PART_REQUEST_UPDATE,
        ),
        empty_message="No activity yet.",
        search_empty_message="No activity matches your search.",
    ),
    "logs": FeedConfig(
        title_suffix=" · Logs",
        breadcrumb_label="Logs",
        entry_types=(ENTRY_TYPE_LOG,),
        empty_message="No log entries yet.",
        search_empty_message="No log entries match your search.",
    ),
    "problems": FeedConfig(
        title_suffix=" · Problem Reports",
        breadcrumb_label="Problems",
        entry_types=(ENTRY_TYPE_PROBLEM_REPORT,),
        empty_message="No problem reports yet.",
        search_empty_message="No problem reports match your search.",
    ),
    "parts": FeedConfig(
        title_suffix=" · Part Requests",
        breadcrumb_label="Parts",
        entry_types=(ENTRY_TYPE_PART_REQUEST,),
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


def get_machine_feed_page(
    machine: MachineInstance,
    entry_types: tuple[str, ...],
    page_num: int,
    page_size: int = settings.LIST_PAGE_SIZE,
    search_query: str | None = None,
) -> tuple[list[FeedEntry], bool]:
    """Get a paginated page of machine activity entries.

    Uses merge-sort style pagination: fetches just enough from each table
    to construct the requested page.

    Args:
        machine: The MachineInstance to get entries for.
        entry_types: Tuple of entry type strings to include.
        page_num: Page number (1-indexed).
        page_size: Number of items per page (default: settings.LIST_PAGE_SIZE).
        search_query: Optional search string to filter results.

    Returns:
        Tuple of (page_items, has_next) where page_items is a list of entries
        and has_next indicates if more pages exist.
    """
    offset = (page_num - 1) * page_size
    # Fetch one extra to detect if more pages exist (countless pagination pattern)
    fetch_limit = offset + page_size + 1

    all_entries: list[FeedEntry] = []

    # Build querysets based on requested entry types
    if ENTRY_TYPE_LOG in entry_types:
        logs = _get_log_entries(machine, search_query, fetch_limit)
        all_entries.extend(logs)

    if ENTRY_TYPE_PROBLEM_REPORT in entry_types:
        reports = _get_problem_reports(machine, search_query, fetch_limit)
        all_entries.extend(reports)

    if ENTRY_TYPE_PART_REQUEST in entry_types:
        part_requests = _get_part_requests(machine, search_query, fetch_limit)
        all_entries.extend(part_requests)

    if ENTRY_TYPE_PART_REQUEST_UPDATE in entry_types:
        part_updates = _get_part_request_updates(machine, search_query, fetch_limit)
        all_entries.extend(part_updates)

    # Sort by occurred_at descending (all entry types)
    combined = sorted(
        all_entries,
        key=lambda x: x.occurred_at,
        reverse=True,
    )

    # Slice to requested page
    page_items = combined[offset : offset + page_size]
    has_next = len(combined) > offset + page_size

    return page_items, has_next


def _get_log_entries(
    machine: MachineInstance, search_query: str | None, limit: int
) -> list[LogEntry]:
    """Get log entries for a machine with optional search filter."""
    queryset = (
        LogEntry.objects.filter(machine=machine)
        .select_related("problem_report")
        .prefetch_related("maintainers__user", "media")
    )

    if search_query:
        queryset = queryset.search_for_machine(search_query)

    queryset = queryset.order_by("-occurred_at")
    logs_list = list(queryset[:limit])

    # Tag entries for template differentiation
    for log in logs_list:
        log.entry_type = ENTRY_TYPE_LOG  # type: ignore[attr-defined]

    return logs_list


def _get_problem_reports(
    machine: MachineInstance, search_query: str | None, limit: int
) -> list[ProblemReport]:
    """Get problem reports for a machine with optional search filter."""
    latest_log_prefetch = Prefetch(
        "log_entries",
        queryset=LogEntry.objects.order_by("-occurred_at"),
        to_attr="prefetched_log_entries",
    )
    queryset = (
        ProblemReport.objects.filter(machine=machine)
        .select_related("reported_by_user")
        .prefetch_related(latest_log_prefetch, "media")
    )

    if search_query:
        queryset = queryset.search_for_machine(search_query)

    queryset = queryset.order_by("-occurred_at")
    reports_list = list(queryset[:limit])

    for report in reports_list:
        report.entry_type = ENTRY_TYPE_PROBLEM_REPORT  # type: ignore[attr-defined]

    return reports_list


def _get_part_requests(
    machine: MachineInstance, search_query: str | None, limit: int
) -> list[PartRequest]:
    """Get part requests for a machine with optional search filter."""
    latest_update_prefetch = Prefetch(
        "updates",
        queryset=PartRequestUpdate.objects.order_by("-occurred_at"),
        to_attr="prefetched_updates",
    )
    queryset = (
        PartRequest.objects.filter(machine=machine)
        .select_related("requested_by__user")
        .prefetch_related("media", latest_update_prefetch)
    )

    if search_query:
        queryset = queryset.search_for_machine(search_query)

    queryset = queryset.order_by("-occurred_at")
    requests_list = list(queryset[:limit])

    for pr in requests_list:
        pr.entry_type = ENTRY_TYPE_PART_REQUEST  # type: ignore[attr-defined]

    return requests_list


def _get_part_request_updates(
    machine: MachineInstance, search_query: str | None, limit: int
) -> list[PartRequestUpdate]:
    """Get part request updates for a machine with optional search filter."""
    queryset = (
        PartRequestUpdate.objects.filter(part_request__machine=machine)
        .select_related("posted_by__user", "part_request")
        .prefetch_related("media")
    )

    if search_query:
        queryset = queryset.search_for_machine(search_query)

    queryset = queryset.order_by("-occurred_at")
    updates_list = list(queryset[:limit])

    for pu in updates_list:
        pu.entry_type = ENTRY_TYPE_PART_REQUEST_UPDATE  # type: ignore[attr-defined]

    return updates_list
