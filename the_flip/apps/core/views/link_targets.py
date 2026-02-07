"""Registry-driven autocomplete endpoints for [[type:ref]] link targets."""

from django.db.models import Q
from django.http import JsonResponse
from django.views import View

from the_flip.apps.core.markdown_links import (
    get_autocomplete_types,
    get_enabled_link_types,
    get_link_type,
)
from the_flip.apps.core.mixins import CanAccessMaintainerPortalMixin

AUTOCOMPLETE_RESULT_LIMIT = 50


class LinkTypesView(CanAccessMaintainerPortalMixin, View):
    """JSON endpoint returning available link types for the type picker."""

    def get(self, request, *args, **kwargs):
        """Return all enabled link types that support autocomplete."""
        return JsonResponse({"types": get_autocomplete_types()})


class LinkTargetsView(CanAccessMaintainerPortalMixin, View):
    """JSON endpoint for link target autocomplete.

    Dispatches to registered link types via the markdown_links registry.
    Each link type defines its own search fields, ordering, and serialization.
    """

    def get(self, request, *args, **kwargs):
        """Return matching link targets based on type and query."""
        link_type_name = request.GET.get("type", "").strip()
        query = request.GET.get("q", "").strip()

        lt = get_link_type(link_type_name)
        if lt is None or not lt.is_enabled():
            valid_names = sorted(t.name for t in get_enabled_link_types())
            return JsonResponse(
                {"error": f"Invalid type. Must be one of: {', '.join(valid_names)}"},
                status=400,
            )

        if not lt.autocomplete_serialize:
            return JsonResponse(
                {"error": f"Type '{link_type_name}' does not support autocomplete"},
                status=400,
            )

        model = lt.get_model()
        qs = model.objects.all()

        if lt.autocomplete_select_related:
            qs = qs.select_related(*lt.autocomplete_select_related)

        if lt.autocomplete_ordering:
            qs = qs.order_by(*lt.autocomplete_ordering)

        if query and lt.autocomplete_search_fields:
            q_filter = Q()
            for field in lt.autocomplete_search_fields:
                q_filter |= Q(**{f"{field}__icontains": query})
            qs = qs.filter(q_filter)

        total_count = qs.count()
        results = [lt.autocomplete_serialize(obj) for obj in qs[:AUTOCOMPLETE_RESULT_LIMIT]]
        return JsonResponse({"results": results, "total_count": total_count})
