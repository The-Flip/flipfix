"""Home page views."""

from django.views import View
from django.views.generic import TemplateView

from the_flip.apps.core.mixins import SharedAccountMixin, can_access_maintainer_portal
from the_flip.apps.core.views.feed import GlobalActivityFeedView


class HomeView(View):
    """Home page: activity feed for maintainers, welcome page for others."""

    def get(self, request):
        if request.user.is_authenticated and can_access_maintainer_portal(request.user):
            return GlobalActivityFeedView.as_view()(request)
        return PublicHomeView.as_view()(request)


class PublicHomeView(SharedAccountMixin, TemplateView):
    """Public landing page for logged-out users or non-maintainers."""

    template_name = "home.html"
