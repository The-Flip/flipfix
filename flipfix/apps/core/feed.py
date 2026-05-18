"""Unified activity feed: paginated entries across multiple models.

Provides a single entry point for fetching activity feeds, supporting both
machine-scoped and global (all machines) views. Machine-scoped feeds filter
by machine and exclude machine name from search. Global feeds include machine
info in select_related for display.

Each record type is registered as a FeedEntrySource via AppConfig.ready(),
so adding a new type means registering one source definition in the owning
app rather than editing this module.  Compare the same pattern in
core/markdown_links.py (link types) and core/models.py (media models).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db.models import QuerySet

if TYPE_CHECKING:
    from collections.abc import Callable

    from flipfix.apps.catalog.models import MachineInstance


_DEFAULT_FEED_ORDER: tuple[str, ...] = ("-occurred_at",)


@dataclass(frozen=True)
class FeedConfig:
    """Configuration for a machine feed filter tab.

    ``source_order_by`` controls the DB ordering applied to each participating
    source queryset.  It defaults to ``("-occurred_at",)``, which matches the
    Python merge-sort comparator in :func:`get_feed_page`.

    **Invariant:** if more than one source participates (``len(entry_types) != 1``,
    which includes ``entry_types=()`` \u2014 the "all registered types" sentinel), the
    sort key must remain ``("-occurred_at",)``.  Pagination fetches a per-source
    slab using ``source_order_by`` and then merges by ``occurred_at`` desc \u2014 if
    the per-source key disagrees with the merge key, the slab is the wrong
    window and entries silently vanish from the result.  Enforced by
    :meth:`__post_init__`.
    """

    title_suffix: str  # Appended to browser title, e.g. "- Logs"
    breadcrumb_label: str | None  # Final breadcrumb text, None for activity feed
    entry_types: tuple[str, ...]  # Which entry types to include; () means all registered
    empty_message: str  # Shown when feed has no entries
    search_empty_message: str  # Shown when search has no results
    source_order_by: tuple[str, ...] = _DEFAULT_FEED_ORDER

    def __post_init__(self) -> None:
        if not self.source_order_by:
            # An empty order tuple would expand to ``QuerySet.order_by()``,
            # which clears all ordering in Django 5.2 and returns rows in
            # unspecified DB order — silently destabilising pagination.
            raise ValueError(
                "FeedConfig.source_order_by cannot be empty; provide at "
                "least one field (e.g. '-occurred_at')."
            )
        if len(self.entry_types) != 1 and self.source_order_by != _DEFAULT_FEED_ORDER:
            raise ValueError(
                "FeedConfig.source_order_by must be ('-occurred_at',) when "
                "entry_types has zero or multiple entries; otherwise the "
                "per-source slab will not align with the merge comparator "
                "and entries can silently drop from paginated results. "
                f"Got entry_types={self.entry_types!r}, "
                f"source_order_by={self.source_order_by!r}."
            )


FEED_CONFIGS: dict[str, FeedConfig] = {
    "all": FeedConfig(
        title_suffix="",
        breadcrumb_label=None,
        entry_types=(),  # empty = all registered types
        empty_message="No activity yet.",
        search_empty_message="No activity matches your search.",
    ),
    "logs": FeedConfig(
        title_suffix=" \u00b7 Logs",
        breadcrumb_label="Logs",
        entry_types=("log",),
        empty_message="No log entries yet.",
        search_empty_message="No log entries match your search.",
    ),
    "problems": FeedConfig(
        title_suffix=" \u00b7 Problem Reports",
        breadcrumb_label="Problems",
        entry_types=("problem_report",),
        empty_message="No problem reports yet.",
        search_empty_message="No problem reports match your search.",
        # `status_sort` and `priority_sort` are CASE annotations applied in
        # MaintenanceConfig._register_feed_sources (maintenance/apps.py).
        # The two declarations must stay in sync \u2014 dropping either side
        # raises FieldError when the Problems tab is rendered.
        source_order_by=("status_sort", "priority_sort", "-occurred_at"),
    ),
    "parts": FeedConfig(
        title_suffix=" \u00b7 Part Requests",
        breadcrumb_label="Parts",
        entry_types=("part_request",),  # updates intentionally excluded (too granular)
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
    - entry_type: string tag set on entries (e.g. "log", "problem_report")
    - get_base_queryset: returns queryset with model-specific select_related/prefetch_related
    - machine_filter_field: field name for .filter(**{field: machine})
    - global_select_related: additional select_related fields for global (non-machine) scope
    - machine_template: template path for rendering in machine-scoped feeds
    - global_template: template path for rendering in global (all-machines) feeds
    """

    entry_type: str
    get_base_queryset: Callable[[], QuerySet[Any]]
    machine_filter_field: str
    global_select_related: tuple[str, ...]
    machine_template: str
    global_template: str


# ---------------------------------------------------------------------------
# Feed source registry
#
# Apps register their FeedEntrySource instances via AppConfig.ready(), keeping
# core free of hardcoded knowledge about other apps.  Compare the same pattern
# in core/markdown_links.py for link-type registration and core/models.py for
# media-model registration.
#
# To add a new entry type to the feed:
# 1. In the owning app's AppConfig.ready(), call register_feed_source()
#    with template paths for machine and global feeds
# 2. Create the entry templates
# That's it — no enums, dispatchers, or other files to edit.
# ---------------------------------------------------------------------------

_feed_source_registry: dict[str, FeedEntrySource] = {}


def register_feed_source(source: FeedEntrySource) -> None:
    """Register a feed entry source. Called from each app's AppConfig.ready()."""
    if source.entry_type in _feed_source_registry:
        raise ValueError(f"Feed source '{source.entry_type}' is already registered")
    _feed_source_registry[source.entry_type] = source


def get_all_entry_types() -> tuple[str, ...]:
    """Return all registered entry type keys. Resolves after AppConfig.ready()."""
    return tuple(_feed_source_registry.keys())


def clear_feed_source_registry() -> None:
    """Reset registry state. For tests only."""
    _feed_source_registry.clear()


def _resolve_entry_types(feed_config: FeedConfig | None) -> tuple[str, ...]:
    """Resolve the entry-type tuple for a feed query.

    ``None`` and an empty ``entry_types`` both mean "all registered types" —
    the convention used by the global activity feed and the All Activity tab.
    """
    if feed_config is None or not feed_config.entry_types:
        return get_all_entry_types()
    return feed_config.entry_types


def get_feed_page(
    page_num: int = 1,
    page_size: int = settings.LIST_PAGE_SIZE,
    search_query: str | None = None,
    machine: MachineInstance | None = None,
    feed_config: FeedConfig | None = None,
) -> tuple[list[Any], bool]:
    """Get a paginated page of activity entries.

    When machine is provided, returns entries scoped to that machine using
    machine-specific search (excludes machine name from search fields).
    When machine is None, returns entries across all machines with global
    search (includes machine name matching).

    ``feed_config=None`` means "all registered types, default ``-occurred_at``
    ordering" — the zero-config behavior used by global activity feeds.
    Otherwise the config supplies both ``entry_types`` and ``source_order_by``;
    its :meth:`FeedConfig.__post_init__` guarantees the per-source key is
    compatible with the merge-sort comparator below.

    For multi-source feeds, uses merge-sort style pagination: fetches just
    enough from each table to construct the requested page.  For single-source
    feeds, skips the Python merge entirely and trusts the DB ordering — this
    is required for correctness, not an optimization, because single-source
    tabs may use a key (e.g. ``status_sort, priority_sort, -occurred_at``)
    that differs from the merge comparator.

    Returns (page_items, has_next) tuple.
    """
    # Both branches arrive safe against the merge-comparator invariant:
    #   - None: implicit default order matches the merge key.
    #   - FeedConfig: __post_init__ guarantees multi-source configs use the
    #     default order; single-source configs may use any key and bypass the
    #     merge below.
    entry_types = _resolve_entry_types(feed_config)
    order_by = feed_config.source_order_by if feed_config else _DEFAULT_FEED_ORDER

    offset = (page_num - 1) * page_size
    # Fetch one extra to detect if more pages exist (countless pagination pattern)
    fetch_limit = offset + page_size + 1

    all_entries: list[Any] = []

    for entry_type in entry_types:
        source = _feed_source_registry.get(entry_type)
        if source:
            all_entries.extend(_fetch_entries(source, machine, search_query, fetch_limit, order_by))

    if len(entry_types) == 1:
        # Single source: DB ordering is already correct; re-sorting by
        # occurred_at would destroy any status/priority bucketing.
        combined = all_entries
    else:
        # Merge sort by occurred_at descending (all entry types share this
        # field, and the invariant guarantees per-source order matches).
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
    order_by: tuple[str, ...],
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

    queryset = queryset.order_by(*order_by)
    entries = list(queryset[:limit])

    # Tag entries with metadata from their source for template rendering
    for entry in entries:
        entry.entry_type = source.entry_type  # type: ignore[attr-defined]
        entry.machine_template = source.machine_template  # type: ignore[attr-defined]
        entry.global_template = source.global_template  # type: ignore[attr-defined]

    return entries
