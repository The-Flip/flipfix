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

    @staticmethod
    def _missing_dimensions(model: MachineModel) -> list[str]:
        """Return the chart dimensions a model is missing (empty if plottable)."""
        missing = []
        if model.year is None:
            missing.append("year")
        if not model.manufacturer:
            missing.append("manufacturer")
        # era can be inferred from the year, so it's only "missing" when neither
        # a stored era nor a year is available.
        if not model.effective_era:
            missing.append("era")
        return missing

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)

        # Partition every owned machine in a single pass: those whose model
        # carries all three chart dimensions are plotted; the rest are listed
        # (with the reason) so a maintainer can find and fix the missing data.
        # ``visible()`` select_related's the model, so reading model fields and
        # ``get_*_display()`` below adds no extra queries.
        owned = MachineInstance.objects.visible().order_by(
            "model__manufacturer", "model__year", "model__sort_name"
        )

        chart_data = []
        excluded = []
        for instance in owned:
            model = instance.model
            missing = self._missing_dimensions(model)
            if missing:
                excluded.append(
                    {
                        "name": instance.short_display_name,
                        "url": reverse("maintainer-machine-detail", args=[instance.slug]),
                        "missing": missing,
                    }
                )
                continue
            era = model.effective_era
            chart_data.append(
                {
                    "name": instance.short_display_name,
                    "manufacturer": model.manufacturer,
                    "year": model.year,
                    "era": era,
                    "era_label": MachineModel.Era(era).label,
                    "status": instance.operational_status,
                    "status_label": instance.get_operational_status_display(),
                    "url": reverse("maintainer-machine-detail", args=[instance.slug]),
                }
            )

        # Excluded machines often lack manufacturer/year, so sort by name.
        excluded.sort(key=lambda m: m["name"].lower())

        context["chart_data"] = chart_data
        context["legend"] = [{"era": era.value, "label": era.label} for era in MachineModel.Era]
        context["excluded"] = excluded
        context["excluded_count"] = len(excluded)
        context["meta_description"] = (
            "Explore The Flip's pinball collection by year, manufacturer and technology era."
        )
        return context
