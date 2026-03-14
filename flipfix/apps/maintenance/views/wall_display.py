"""Wall display views: setup and full-screen board."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.views.generic import TemplateView

from flipfix.apps.catalog.models import Location
from flipfix.apps.core.columns import build_location_columns
from flipfix.apps.maintenance.models import ProblemReport

if TYPE_CHECKING:
    from flipfix.apps.catalog.models import MachineInstance

MIN_REFRESH_SECONDS = 10
MAX_VISIBLE_REPORTS = 4


@dataclass
class MachineGroup:
    """A single machine and its open problem reports for the wall display."""

    machine: MachineInstance
    reports: list[ProblemReport]

    @property
    def sort_key(self) -> int:
        """Sort by the most severe (lowest priority_sort) report.

        ``priority_sort`` is an annotation added by
        :meth:`~flipfix.apps.maintenance.models.ProblemReportQuerySet.for_wall_display`.
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


def _group_by_machine(reports: list[ProblemReport]) -> list[MachineGroup]:
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


class WallDisplaySetupView(TemplateView):
    """Configuration page for the wall display board."""

    template_name = "maintenance/wall_display_setup.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["locations"] = Location.objects.all()
        return context


class WallDisplayBoardView(TemplateView):
    """Full-screen wall display showing open problems by location."""

    template_name = "maintenance/wall_display_board.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        location_slugs = self.request.GET.getlist("location")

        if not location_slugs:
            context["error"] = "No locations specified."
            context["columns"] = []
            context["refresh_seconds"] = None
            return context

        # Parse refresh parameter
        refresh_seconds = None
        raw_refresh = self.request.GET.get("refresh")
        if raw_refresh:
            try:
                value = int(raw_refresh)
                if value >= MIN_REFRESH_SECONDS:
                    refresh_seconds = value
            except (ValueError, TypeError):
                pass

        locations_by_slug = {
            loc.slug: loc for loc in Location.objects.filter(slug__in=location_slugs)
        }
        invalid_slugs = [s for s in location_slugs if s not in locations_by_slug]

        if invalid_slugs:
            joined = ", ".join(f'"{s}"' for s in invalid_slugs)
            context["error"] = f"Unknown location: {joined}."
            context["columns"] = []
            context["refresh_seconds"] = None
            return context

        # Preserve URL param order so the setup page's drag order controls columns.
        locations = [locations_by_slug[s] for s in location_slugs]

        reports = ProblemReport.objects.for_wall_display(location_slugs)
        # No column-level cap: each MachineGroup handles its own overflow
        # via MAX_VISIBLE_REPORTS + overflow_summary.
        columns = build_location_columns(reports, locations)
        # Replace flat report lists with MachineGroup objects
        for column in columns:
            column.items = _group_by_machine(column.items)
        context["columns"] = columns
        context["refresh_seconds"] = refresh_seconds
        return context
