"""Views for the machine "Explore" page (collection visualizations)."""

from typing import Any

from django.urls import reverse
from django.views.generic import TemplateView

from flipfix.apps.catalog.models import MachineInstance, MachineModel


class MachineExploreView(TemplateView):
    """Public page that visualizes the collection.

    The first visualization is a dot chart of physical machines plotted by year
    (x) and manufacturer (y), colored by technology era. Each dot is one
    :class:`MachineInstance`, so owning two copies of a title yields two dots.

    The view stays deliberately thin: it emits a flat, library-agnostic list of
    dot records and lets the client compute scales, manufacturer ordering and
    stacking. This keeps the layout responsive to viewport width and makes a
    future swap of the rendering layer (e.g. Observable Plot) a client-only
    change.
    """

    template_name = "catalog/explore.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)

        # Only machines whose model carries all three chart dimensions can be
        # plotted. ``visible()`` select_related's the model, so reading
        # model fields and ``get_*_display()`` below adds no extra queries.
        owned = MachineInstance.objects.visible()
        instances = (
            owned.filter(model__year__isnull=False)
            .exclude(model__manufacturer="")
            .exclude(model__era="")
            .order_by("model__manufacturer", "model__year", "model__sort_name")
        )

        chart_data = [
            {
                "name": instance.short_display_name,
                "manufacturer": instance.model.manufacturer,
                "year": instance.model.year,
                "era": instance.model.era,
                "era_label": instance.model.get_era_display(),
                "status": instance.operational_status,
                "status_label": instance.get_operational_status_display(),
                "url": reverse("maintainer-machine-detail", args=[instance.slug]),
            }
            for instance in instances
        ]

        context["chart_data"] = chart_data
        context["legend"] = [{"era": era.value, "label": era.label} for era in MachineModel.Era]
        # Count exclusions against the same base queryset chart_data is built
        # from, so the two stay consistent (chart_data is always a subset).
        context["excluded_count"] = owned.count() - len(chart_data)
        context["meta_description"] = (
            "Explore The Flip's pinball collection by year, manufacturer and technology era."
        )
        return context
