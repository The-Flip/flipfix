"""Wall display views: setup and full-screen board."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from django.db.models import F
from django.views.generic import TemplateView

from flipfix.apps.catalog.models import Location, MachineInstance
from flipfix.apps.core.columns import Column, build_location_columns, group_by_machine
from flipfix.apps.maintenance.models import ProblemReport


@dataclass
class NowPlayingColumn:
    """A location's machines plus how many sub-columns it should occupy.

    `sub_columns` lets the outer flex container size each location
    proportionally to its content, so a location with 30 machines gets
    more horizontal space than one with 5.
    """

    label: str
    items: list[MachineInstance]
    sub_columns: int


MIN_REFRESH_SECONDS = 10
DEFAULT_PER_COLUMN = 10
MIN_PER_COLUMN = 1
MAX_PER_COLUMN = 50


class WallDisplayMode:
    """The two display modes the wall board can render."""

    WORKSHOP = "workshop"
    NOW_PLAYING = "now-playing"
    CHOICES = [(WORKSHOP, "Workshop"), (NOW_PLAYING, "Now Playing")]
    DEFAULT = WORKSHOP
    _VALID = {WORKSHOP, NOW_PLAYING}

    @classmethod
    def normalize(cls, value: str | None) -> str:
        return value if value in cls._VALID else cls.DEFAULT


_MODE_CARD_TEMPLATE = {
    WallDisplayMode.WORKSHOP: "maintenance/partials/wall_display_entry.html",
    WallDisplayMode.NOW_PLAYING: "maintenance/partials/wall_display_now_playing_entry.html",
}

_MODE_EMPTY_MESSAGE = {
    WallDisplayMode.WORKSHOP: "No open problems 🥳",
    WallDisplayMode.NOW_PLAYING: "No machines playing.",
}

_MODE_PAGE_TITLE = {
    WallDisplayMode.WORKSHOP: "Problems",
    WallDisplayMode.NOW_PLAYING: "Now Playing",
}


class WallDisplaySetupView(TemplateView):
    """Configuration page for the wall display board."""

    template_name = "maintenance/wall_display_setup.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["locations"] = Location.objects.all()
        context["mode"] = WallDisplayMode.normalize(self.request.GET.get("mode"))
        context["mode_choices"] = WallDisplayMode.CHOICES
        context["default_per_column"] = DEFAULT_PER_COLUMN
        return context


class WallDisplayBoardView(TemplateView):
    """Full-screen wall display showing open problems by location."""

    template_name = "maintenance/wall_display_board.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        mode = WallDisplayMode.normalize(self.request.GET.get("mode"))
        context["mode"] = mode
        context["card_template"] = _MODE_CARD_TEMPLATE[mode]
        context["empty_message"] = _MODE_EMPTY_MESSAGE[mode]
        context["page_title"] = _MODE_PAGE_TITLE[mode]

        location_slugs = self.request.GET.getlist("location")

        if not location_slugs:
            context["error"] = "No locations specified."
            context["columns"] = []
            context["refresh_seconds"] = None
            return context

        refresh_seconds = None
        raw_refresh = self.request.GET.get("refresh")
        if raw_refresh:
            try:
                value = int(raw_refresh)
                if value >= MIN_REFRESH_SECONDS:
                    refresh_seconds = value
            except (ValueError, TypeError):
                pass

        context["per_column"] = _parse_per_column(self.request.GET.get("per_column"))

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

        if mode == WallDisplayMode.NOW_PLAYING:
            columns = _build_now_playing_columns(location_slugs, locations, context["per_column"])
        else:
            columns = _build_workshop_columns(location_slugs, locations)

        context["columns"] = columns
        context["refresh_seconds"] = refresh_seconds
        return context


def _parse_per_column(raw: str | None) -> int:
    if not raw:
        return DEFAULT_PER_COLUMN
    try:
        value = int(raw)
    except (ValueError, TypeError):
        return DEFAULT_PER_COLUMN
    return max(MIN_PER_COLUMN, min(MAX_PER_COLUMN, value))


def _build_workshop_columns(location_slugs: list[str], locations: list[Location]) -> list[Column]:
    reports = ProblemReport.objects.for_wall_display(location_slugs)
    # No column-level cap: each MachineGroup handles its own overflow
    # via MAX_VISIBLE_REPORTS + overflow_summary.
    columns = build_location_columns(reports, locations)
    # Replace flat report lists with MachineGroup objects
    for column in columns:
        column.items = group_by_machine(column.items)
    return columns


def _build_now_playing_columns(
    location_slugs: list[str], locations: list[Location], per_column: int
) -> list[NowPlayingColumn]:
    machines = (
        MachineInstance.objects.filter(
            operational_status=MachineInstance.OperationalStatus.GOOD,
            location__slug__in=location_slugs,
        )
        .select_related("model", "location")
        .order_by(F("model__year").asc(nulls_last=True), "name")
    )
    by_location: dict[int, list[MachineInstance]] = defaultdict(list)
    for machine in machines:
        by_location[machine.location_id].append(machine)
    result = []
    for location in locations:
        items = by_location.get(location.pk, [])
        # At least 1 so empty locations still claim a slice of horizontal space.
        sub_columns = max(1, math.ceil(len(items) / per_column))
        result.append(NowPlayingColumn(label=location.name, items=items, sub_columns=sub_columns))
    return result
