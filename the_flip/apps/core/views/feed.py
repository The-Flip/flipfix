"""Global activity feed views."""

from django.http import JsonResponse
from django.template.loader import render_to_string
from django.views import View
from django.views.generic import TemplateView

from the_flip.apps.core.feed import PageCursor, get_feed_page
from the_flip.apps.core.forms import SearchForm
from the_flip.apps.core.mixins import CanAccessMaintainerPortalMixin
from the_flip.apps.maintenance.models import ProblemReport
from the_flip.apps.parts.models import PartRequest


class GlobalActivityFeedView(CanAccessMaintainerPortalMixin, TemplateView):
    """Global activity feed showing all entries across all machines."""

    template_name = "core/global_activity_feed.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search_query = self.request.GET.get("q", "").strip()

        # Get first page of entries
        entries, has_next = get_feed_page(
            page_num=1,
            search_query=search_query or None,
        )

        # Stats for sidebar - actionable items
        stats = [
            {
                "value": ProblemReport.objects.filter(status=ProblemReport.Status.OPEN).count(),
                "label": "Open Problems",
            },
            {
                "value": PartRequest.objects.filter(status=PartRequest.Status.REQUESTED).count(),
                "label": "Parts Req'd",
            },
        ]

        context.update(
            {
                "entries": entries,
                "page_obj": PageCursor(has_next=has_next, page_num=1),
                "search_form": SearchForm(initial={"q": search_query}),
                "stats": stats,
            }
        )
        return context


class GlobalActivityFeedPartialView(CanAccessMaintainerPortalMixin, View):
    """AJAX endpoint for infinite scroll on global activity feed."""

    def get(self, request):
        try:
            page_num = int(request.GET.get("page", 1))
        except (TypeError, ValueError):
            page_num = 1

        search_query = request.GET.get("q", "").strip() or None

        page_items, has_next = get_feed_page(
            page_num=page_num,
            search_query=search_query,
        )

        items_html = "".join(
            render_to_string(
                "core/partials/global_activity_entry.html",
                {"entry": entry},
            )
            for entry in page_items
        )

        return JsonResponse(
            {
                "items": items_html,
                "has_next": has_next,
                "next_page": page_num + 1 if has_next else None,
            }
        )
