"""Wall display views: setup and full-screen board."""

from __future__ import annotations

from django.views.generic import TemplateView

from the_flip.apps.catalog.models import Location
from the_flip.apps.core.columns import build_location_columns
from the_flip.apps.core.mixins import CanAccessMaintainerPortalMixin
from the_flip.apps.maintenance.models import ProblemReport

MIN_REFRESH_SECONDS = 10


class WallDisplaySetupView(CanAccessMaintainerPortalMixin, TemplateView):
    """Configuration page for the wall display board."""

    template_name = "maintenance/wall_display_setup.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["locations"] = Location.objects.all()
        return context


class WallDisplayBoardView(CanAccessMaintainerPortalMixin, TemplateView):
    """Full-screen wall display showing open problems by location."""

    template_name = "maintenance/wall_display_board.html"
    max_results_per_column = 20

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
        context["columns"] = build_location_columns(
            reports, locations, max_results_per_column=self.max_results_per_column
        )
        context["refresh_seconds"] = refresh_seconds
        return context
